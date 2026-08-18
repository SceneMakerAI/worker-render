"""렌더 — 조각을 하나씩 만들고(cut) 이어붙인다(concat).

시간은 사실상 전부 cut 이다 (실측 조각당 1.3s, concat 은 200MB 에 0.26s).
"""
import logging
import shutil
import threading
from concurrent.futures import Future, ThreadPoolExecutor, wait
from pathlib import Path

import config
from lib import util
from lib.dto import MediaInfo, ReqTimeRange, ResRender
from lib.media import ffmpeg
from lib.storage import s3

log = logging.getLogger(__name__)

# 워커 1개 = ffmpeg 1개. 동시에 띄우면 NVDEC 컨텍스트가 입력당 400MB 넘게 붙어 GPU 가 터진다.
# FastAPI 는 def 핸들러를 자기 스레드풀(기본 40개)에서 돌리므로 여기로 모아 직렬화한다.
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="render")

# 잡 상태는 Future 자체다 — accepted/running/done/error 를 다 알고 있어서 따로 들 이유가 없다.
# 재기동하면 사라지지만, 그때는 결과 파일 존재로 done 을 복원한다.
_lock = threading.Lock()
_jobs: dict[tuple[int, int], Future] = {}
_KEEP_FINISHED = 100        # 끝난 잡을 몇 개까지 기억할지 (Future 가 인자를 붙들고 있어 무한정 두면 샌다)


class QueueFull(RuntimeError):
    """대기열이 가득 찼다. 호출부가 429 로 옮긴다."""


def make_output_filename(v_id: int, c_id: int) -> Path:
    """{OUTPUT_DATA_DIR}/{v_id}/{v_id}_{c_id}.mp4 (절대경로)."""
    return (config.OUTPUT_DATA_DIR / str(v_id) / f"{v_id}_{c_id}.mp4").resolve()


def cut_parts(parts: list[ReqTimeRange], media_info: MediaInfo, work: Path) -> list[Path]:
    """조각을 하나씩 잘라 work 에 만든다. 규격은 원본(media_info)에 맞춘다.

    한 번에 하나씩이어야 한다 — filter_complex 로 입력 수십 개를 동시에 열면 GPU 가 터진다
    (24GB 카드에서 조각 86개 중 61번째에 CUDA_ERROR_OUT_OF_MEMORY, 실측).
    """
    files: list[Path] = []
    for i, part in enumerate(parts):
        dst = work / f"p{i:03d}.mp4"
        start, end = (None, None) if part.whole_file else (part.start_sec, part.end_sec)
        span = "전체" if part.whole_file else f"{util.hms(start)}~{util.hms(end)}"
        log.info(f"{work} cut {i + 1}/{len(parts)} {part.src.name} {span} → {dst.name}")
        files.append(ffmpeg.cut_encode(part.src, dst, media_info.width, media_info.height,
                                       media_info.fps, start, end))
    return files


def render(files: list[Path], work: Path, out: Path) -> Path:
    """조각을 순서대로 이어붙인다 (stream copy).

    work 에 만들고 다 되면 옮긴다 — out 에 바로 쓰면 ffmpeg 이 파일을 여는 순간 기존 결과물이
    날아가서, 재처리가 실패하면 새것도 옛것도 없어진다.
    """
    final = work / "final.mp4"
    log.info(f"{work} concat {len(files)} parts → {out}")
    ffmpeg.concat(files, final, work)

    final.replace(out)          # 같은 파일시스템이라 rename — 원자적
    return out


def start(v_id: int, c_id: int, parts: list[ReqTimeRange], media_info: MediaInfo,
          sync: bool = False) -> ResRender:
    """워커에 넘기고 응답을 만든다. sync 면 끝날 때까지 기다린다.

    sync 든 아니든 워커는 하나다 — 동기는 "직접 돈다"가 아니라 "줄 서서 기다린다".
    이미 돌고 있는 (v_id, c_id) 면 재실행하지 않고 현재 상태를 준다. 끝난 잡은 재접수 가능(덮어쓰기).
    대기열이 꽉 차면 QueueFull — 호출부가 429 로 옮긴다.
    """
    key = (v_id, c_id)
    out = make_output_filename(v_id, c_id)
    work = out.parent / f"work_{c_id}"

    # 등록까지 한 번에 잠근다. 검사와 submit 이 벌어지면 동시 요청이 상한을 넘어 들어온다.
    with _lock:
        cur = _jobs.get(key)
        if cur is not None and not cur.done():
            log.info(f"[{v_id}/{c_id}] 이미 진행 중 — 재접수 무시")
            return _to_res(cur, out)

        busy = sum(1 for f in _jobs.values() if not f.done())
        if busy >= config.MAX_THREAD_QUEUE:
            raise QueueFull(f"렌더 대기열이 가득 찼습니다 ({busy}/{config.MAX_THREAD_QUEUE})")

        # 디렉토리는 submit 전에 만든다 — 스레드 안에서 터지면 폴링해야만 알 수 있다
        shutil.rmtree(work, ignore_errors=True)     # 재처리 대비 — 옛 조각이 섞이지 않도록
        work.mkdir(parents=True, exist_ok=True)     # parents=True 가 출력 디렉토리까지 만든다

        future = _executor.submit(_cut_and_render, parts, media_info, work, out)
        _jobs[key] = future
        _forget_old()

    if not sync:
        return ResRender(status="accepted", output_path=str(out))

    wait([future])                  # 끝나기만 기다린다 — 성공/실패 판정은 _to_res 가 한다
    return _to_res(future, out)


def status(v_id: int, c_id: int) -> ResRender | None:
    """메모리에 잡이 있으면 그 상태, 없으면 결과 파일 존재로 done 판정. 둘 다 없으면 None."""
    out = make_output_filename(v_id, c_id)
    with _lock:
        future = _jobs.get((v_id, c_id))

    if future is not None:
        return _to_res(future, out)
    if out.exists():                            # 재기동으로 메모리가 비어도 결과물이 있으면 done
        return ResRender(status="done", output_path=str(out))
    return None


def _to_res(future: Future, out: Path) -> ResRender:
    """Future 하나가 곧 상태다 — 따로 들고 있으면 진실이 두 곳이 된다.

    큐에 있으면 accepted, 돌고 있으면 running, 끝났으면 예외 유무로 done/error.
    output_path 는 done 일 때만 채운다 (접수 응답과 다른 지점).
    """
    if not future.done():
        return ResRender(status="running" if future.running() else "accepted")

    exc = future.exception()
    if exc is not None:
        return ResRender(status="error", error=str(exc))
    return ResRender(status="done", output_path=str(out))


def _forget_old():
    """끝난 잡이 쌓이면 오래된 것부터 버린다. 버려져도 결과 파일로 done 판정되므로 안전하다."""
    finished = [k for k, f in _jobs.items() if f.done()]
    for key in finished[:max(0, len(finished) - _KEEP_FINISHED)]:
        del _jobs[key]


def _cut_and_render(parts: list[ReqTimeRange], media_info: MediaInfo, work: Path,
                    out: Path) -> Path:
    """워커 스레드 본체. 중간 조각은 끝나면 정리한다 (config 로 보존 가능).

    S3URL 이 설정돼 있으면 {S3URL}/{v_id}/{v_id}_{c_id}.mp4 로 올린다. 업로드가 실패하면 잡도
    error 다 — 로컬에만 있고 전달이 안 된 걸 done 이라 하면 부르는 쪽이 없는 걸 가져가려 한다.
    """
    try:
        files = cut_parts(parts, media_info, work)
        result = render(files, work, out)
        if s3.enabled():
            s3.upload(result, f"{out.parent.name}/{out.name}")
            # 원본에서 어떻게 잘렸는지 — 범퍼(0~0)는 우리가 끼운 거라 뺀다
            s3.upload_json([p.model_dump(exclude={"src"}) for p in parts if not p.whole_file],
                           f"{out.parent.name}/{out.stem}.json")
    except Exception:
        # 여기서 안 찍으면 비동기 실패는 아무 데도 안 남는다 — Future 를 아무도 안 꺼내보므로
        log.exception(f"{work} render failed")
        _clean_work(work, config.DELETE_WORK_DIR["ERROR"])
        raise
    _clean_work(work, config.DELETE_WORK_DIR["SUCCESS"])
    return result


def _clean_work(work: Path, delete: int):
    if delete:
        shutil.rmtree(work, ignore_errors=True)
    else:
        log.info(f"중간 조각 보존 — {work}")

