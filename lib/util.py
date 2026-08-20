"""잡동사니 헬퍼 — 시간 표기, 경로 조립."""
from pathlib import Path

import config


def hms(sec: float) -> str:
    """초 → hh:mm:ss.f. 로그 표기용 (요청의 *_hms 는 신뢰하지 않고 sec 에서 다시 만든다)."""
    h, rem = divmod(max(sec, 0.0), 3600)
    m, s = divmod(rem, 60)
    return f"{int(h):02d}:{int(m):02d}:{s:04.1f}"


def vod_paths(v_id: int) -> tuple[Path, Path]:
    """v_id 폴더와 그 안의 원본 파일 경로.

        ({VOD_DIR}/{v_id}, {VOD_DIR}/{v_id}/source.mp4)

    로컬은 폴더가 v_id 라 파일명은 source.mp4 로 고정이다. S3 는 폴더가 v_id%50 이라 파일명에
    v_id 가 들어가고(s3_paths), 그래서 양쪽 이름이 다르다.

    조립만 한다 — 디렉토리는 만들지 않는다. 조회 API 도 이 경로로 파일 존재만 확인하는데,
    여기서 mkdir 을 하면 없는 잡을 폴링할 때마다 빈 디렉토리가 생긴다.
    """
    vod_dir = config.VOD_DIR / str(v_id)
    return vod_dir, vod_dir / "source.mp4"


def s3_paths(v_id: int) -> tuple[str, str]:
    """S3 에 있는 원본의 폴더와 파일 주소. 받아오는 곳은 S3URL 의 **첫 번째**.

        ({S3URL[0]}/vod/{v_id % 50}, {S3URL[0]}/vod/{v_id % 50}/{v_id}.mp4)

    v_id 를 50 으로 나눈 나머지로 폴더를 나눈다 — 한 폴더에 파일이 몰리지 않게 하려는 것으로,
    t_video.dir 규칙과 같다 (v_id 201 → vod/1/201.mp4, v_id 200 → vod/0/200.mp4).
    """
    s3_dir = f"{config.S3URL[0]}/vod/{v_id % 50}"
    return s3_dir, f"{s3_dir}/{v_id}.mp4"


def render_paths(v_id: int, c_id: int) -> tuple[Path, Path, Path]:
    """편성 하나가 쓰는 경로 셋 — (결과물, 사이드카, 작업 디렉토리).

        {VOD_DIR}/{v_id}/result/{v_id}_{c_id}.mp4
        {VOD_DIR}/{v_id}/result/{v_id}_{c_id}.json
        {VOD_DIR}/{v_id}/work_{c_id}/

    결과물을 result/ 아래 두어 원본과 섞이지 않게 하고, S3 의 result/ 와 모양을 맞춘다.
    작업 디렉토리에 c_id 가 들어가는 건 같은 영상을 여러 편성이 동시에 렌더해도 조각이
    안 섞이게 하려는 것이다.
    """
    vod_dir, _ = vod_paths(v_id)
    result_dir = vod_dir / "result"
    return ((result_dir / f"{v_id}_{c_id}.mp4").resolve(),
            (result_dir / f"{v_id}_{c_id}.json").resolve(),
            (vod_dir / f"work_{c_id}").resolve())


def s3_result_paths(s3url: str, v_id: int, c_id: int) -> tuple[str, str]:
    """업로드 대상 하나에 대한 (영상 주소, JSON 주소).

        ({s3url}/result/{v_id}/{v_id}_{c_id}.mp4,
         {s3url}/result/{v_id}/{v_id}_{c_id}.json)

    여러 곳에 올릴 때는 부르는 쪽이 config.S3URL 을 돌면서 하나씩 넘긴다.
    """
    return (f"{s3url}/result/{v_id}/{v_id}_{c_id}.mp4",
            f"{s3url}/result/{v_id}/{v_id}_{c_id}.json")
