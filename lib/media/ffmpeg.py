# probe / cut_encode / concat — 각각 ffmpeg 호출 한 개씩만 담당한다.
# -c copy 로 붙이지 않고 재인코딩하는 이유:
# 스트림 복사는 키프레임에서만 시작할 수 있는데 원본 키프레임 간격이 5초라
# 평균 16초짜리 하이라이트에서 컷이 최대 5초까지 밀린다.
# 모든 파트는 원본 스펙으로 정규화하며, 원본 이상으로 업스케일하지 않는다.

"""ffmpeg primitive — 슬림 버전 (ffmpeg.py 대안).

함수 3개:
    probe    영상인지 확인 + 규격(해상도/fps/오디오/길이) 읽기
    ffmpeg   구간을 잘라 표준 규격의 조각으로 만듦. 구간을 안 주면 통째로 변환 (범퍼용)
    concat   조각들을 이어붙여 최종 파일

ffmpeg.py 의 cut / normalize 는 "구간을 자르냐 마냐"만 달랐고 인코딩 인자는 같았다.
ffmpeg() 하나로 합치면서 인자 조립 헬퍼(_input_args/_encode_args)도 없앴다.

concat 으로 이어붙이려면 조각의 코덱·해상도·fps·오디오 규격·타임베이스가 모두 같아야 한다.
그래서 조각을 전부 같은 규격(target)으로 재인코딩한 뒤 stream copy 로 합친다.
target 은 원본에서 뽑아 쓴다 — 720p 원본을 1080p 로 올리는 낭비를 피하고 범퍼를 원본에 맞춘다.

장시간(4~5시간) 원본이라도 `-ss` 를 `-i` 앞에 두면 인덱스로 점프하므로, 실제 디코드는
잘라내는 구간 길이만큼만 일어난다. 디코드 NVDEC, 인코드 NVENC.
"""
import json
import logging
import subprocess
from functools import lru_cache
from pathlib import Path

import config

log = logging.getLogger(__name__)

TIMEOUT = 3600          # s — 구간 하나 기준으로는 과할 만큼 넉넉히
AUDIO_RATE = 48000


def _run(cmd: list[str], timeout: int = TIMEOUT) -> str:
    """리스트 인자로 실행 (경로에 공백/따옴표가 있어도 안전). 실패하면 stderr 꼬리를 담아 예외."""
    log.info(f"$ {' '.join(cmd)}")
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(f"{Path(cmd[0]).name} failed ({proc.returncode}): "
                           f"{proc.stderr.strip()[-500:]}")
    return proc.stdout


@lru_cache(maxsize=256)
def probe(path: Path) -> dict:
    """duration / 해상도 / fps / 오디오 유무. 영상 스트림이 없으면 RuntimeError.

    fps 는 분수 문자열('30000/1001') 그대로 쓴다 — 29.97 로 반올림하면 긴 영상에서 오디오와 어긋난다.

    **경로 기준으로 캐시한다.** 구간 69개가 전부 같은 원본이면 9.7GB 파일을 69번 다시 여는 셈이라
    조각마다 ffprobe 가 하나씩 더 뜬다. 렌더 도중 원본이 바뀌지는 않으므로 캐시가 안전하다.
    (파일이 실제로 교체되는 상황이 생기면 probe.cache_clear() 로 비운다.)
    """
    out = _run([str(config.FFMPEG_DIR / "ffprobe"), "-v", "error", "-print_format", "json",
                "-show_format", "-show_streams", str(path)], timeout=60)
    data = json.loads(out)
    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    audio = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), None)
    if video is None:
        raise RuntimeError(f"영상 스트림이 없습니다: {path}")

    fps = video.get("r_frame_rate", "30/1")
    if fps in ("0/0", "0/1"):                       # 일부 컨테이너는 r_frame_rate 를 못 준다
        fps = video.get("avg_frame_rate", "30/1")

    info = {"duration": float(data.get("format", {}).get("duration", 0.0)),
            "width": int(video["width"]), "height": int(video["height"]),
            "fps": fps, "has_audio": audio is not None}
    log.info(f"probe {Path(path).name} → {info}")
    return info


def cut_encode(src: Path, out: Path, width: int, height: int, fps: str,
               start_sec: float | None = None, end_sec: float | None = None) -> Path:
    """src 를 잘라 width/height/fps 규격의 mp4 조각으로 만든다 (재인코딩).

    start_sec/end_sec 를 주면 그 구간만 (하이라이트 컷), 안 주면 통째로 (범퍼 규격 맞추기).
    범퍼도 규격이 달라(24fps/96kHz) 재인코딩이 필요하므로, 안 자를 뿐 인코딩 인자는 같다.

    무음 소스는 anullsrc 로 무음 트랙을 채운다 — 오디오가 없는 조각이 섞이면 concat 이 깨진다.
    """
    silent = not probe(src)["has_audio"]     # 같은 파일은 캐시라 조각마다 다시 안 띄운다
    ff = [str(config.FFMPEG_DIR / "ffmpeg"), "-y", "-hide_banner", "-loglevel", "error",
          "-hwaccel", "cuda", "-hwaccel_output_format", "cuda",
          "-hwaccel_device", str(config.GPU_NUM)]

    if start_sec is not None:
        ff += ["-ss", f"{start_sec:.3f}"]           # -i 앞 = 입력 seek (인덱스 점프, 빠름)
    ff += ["-i", str(src)]
    if silent:
        ff += ["-f", "lavfi", "-i", f"anullsrc=channel_layout=stereo:sample_rate={AUDIO_RATE}"]
    if start_sec is not None and end_sec is not None:
        ff += ["-t", f"{end_sec - start_sec:.3f}"]

    ff += [
        "-map", "0:v:0", "-map", "1:a:0" if silent else "0:a:0",
        # fps 를 먼저 맞춰 버릴 프레임은 스케일하지 않는다. scale_cuda 는 GPU.
        "-vf", f"fps={fps},scale_cuda={width}:{height}:format=nv12",
        "-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "21",
        "-g", "60", "-fps_mode", "cfr",             # 조각 첫 프레임이 키프레임이어야 concat 이 안전
        "-c:a", "aac", "-b:a", "192k", "-ar", str(AUDIO_RATE), "-ac", "2",
        "-video_track_timescale", "90000",          # 조각 간 타임베이스 통일
    ]
    if silent:
        ff += ["-shortest"]                         # anullsrc 는 무한이라 이게 없으면 안 끝난다
    ff += [str(out)]

    _run(ff)
    return out


def concat(parts: list[Path], out: Path, work_dir: Path) -> Path:
    """조각들을 순서대로 이어붙임 (concat demuxer + -c copy). 조각 규격이 같다는 전제."""
    list_file = work_dir / "concat.txt"
    # concat demuxer 는 경로를 작은따옴표로 감싸므로, 경로 안의 작은따옴표를 이스케이프
    lines = []
    for p in parts:
        escaped = str(p.resolve()).replace("'", "'\\''")
        lines.append(f"file '{escaped}'")
    list_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    _run([str(config.FFMPEG_DIR / "ffmpeg"), "-y", "-hide_banner", "-loglevel", "error",
          "-f", "concat", "-safe", "0", "-i", str(list_file),
          "-c", "copy", "-movflags", "+faststart", str(out)])
    return out
