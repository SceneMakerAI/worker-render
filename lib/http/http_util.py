"""HTTP 미들웨어 — 요청/응답 로깅 + 에러 응답 헬퍼 + 입력 검증.

main.py 에서 register(app) 로 등록.

검증은 두 층으로 나눈다:
  문법 (타입·필수 필드)   pydantic → RequestValidationError 핸들러가 400 으로 통일. 앱 레벨 1곳.
  도메인 (파일·구간)      각 종목 핸들러가 check_video 를 호출. API 마다 볼 게 다르므로.

check_video 는 HTTP 계층에 있으므로 HTTPException 을 바로 던진다 — 핸들러에 try/except 가 필요 없다.
"""
import logging
import time
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

import config
from lib import util
from lib.dto import MediaInfo, ReqTimeRanges
from lib.media import ffmpeg
from lib.storage import s3


def register(app):
    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        logging.info(f"→ {request.method} {request.url}")
        t0 = time.time()
        response = await call_next(request)
        logging.info(f"← {request.method} {request.url} {response.status_code} ({time.time() - t0:.1f}s)")
        return response

    @app.exception_handler(RequestValidationError)
    async def on_validation_error(request: Request, exc: RequestValidationError):
        """pydantic 검증 실패(기본 422 + detail 배열)를 스펙 형태의 400 으로 통일.

        기본 응답은 detail 이 배열이라 {"detail": {"code", "message"}} 계약이 깨진다.
        이 핸들러는 라우터 진입 **전**에 걸리는 요청도 잡으므로, 로그에도 여기서 남긴다.
        """
        message = "; ".join(
            f"{'.'.join(str(x) for x in e['loc'][1:]) or 'body'}: {e['msg']}"
            for e in exc.errors()
        )
        logging.warning(f"✗ {request.method} {request.url} 400 INVALID_REQUEST — {message}")
        return JSONResponse(status_code=400,
                            content={"detail": {"code": "INVALID_REQUEST", "message": message}})


def log_req(req):
    """요청 body 로깅. pydantic 모델은 repr 에 클래스명+필드가 들어감."""
    logging.info(f"req  {req!r}")


def log_res(res):
    """응답 body 로깅."""
    logging.info(f"res  {res!r}")


def err(status_code: int, code: str, message: str) -> HTTPException:
    """{"detail": {"code": ..., "message": ...}} 형태의 에러 응답.

    FastAPI 는 detail 을 그대로 직렬화하므로 dict 를 넘기면 스펙 형태가 나온다.
    """
    logging.warning(f"✗ {status_code} {code} — {message}")
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def download_video(v_id: int) -> Path:
    """렌더에 쓸 원본의 로컬 경로를 돌려준다. 필요하면 S3 에서 받아온다.

    S3URL 이 비어 있으면 로컬만 본다. 있으면 매번 S3 와 크기를 비교하는데, 같으면
    download_file 이 알아서 건너뛴다 — 원본이 갱신된 경우를 놓치지 않으려는 것이다.

    받아올 곳은 S3URL 의 **첫 번째**. 수십 GB 라 실제로 받으면 몇 분 걸리고, 그동안 요청
    스레드가 붙잡혀 있다. S3 에도 없으면 404 로 끝난다.
    """
    vod_dir, local_file = util.vod_paths(v_id)

    if not config.S3URL:                # S3 를 안 쓰는 환경 — 로컬에 있는 것만 쓴다
        if not local_file.exists():
            raise err(404, "SOURCE_NOT_FOUND", f"원본이 없습니다: {local_file}")
        return local_file

    _, s3_file = util.s3_paths(v_id)
    try:
        vod_dir.mkdir(parents=True, exist_ok=True)
        s3.download_file(s3_file, local_file)
    except Exception as e:              # noqa: BLE001 — 못 받으면 원본이 없는 것과 같다
        raise err(404, "SOURCE_NOT_FOUND",
                  f"원본을 S3 에서 받지 못했습니다: s3_file={s3_file}, local_file={local_file} ({e})")

    return local_file



def check_video_format(file_path: Path | str, groups: dict[str, ReqTimeRanges]) -> MediaInfo:
    """영상 파일과 구간을 한 번에 검사하고 MediaInfo 를 돌려준다.

    확장자만 보면 이름만 .mp4 인 텍스트 파일을 통과시키므로 ffprobe 로 실제 영상 스트림까지 확인한다.
    구간까지 여기서 보는 이유는 원본 길이(ffprobe 결과)와 비교해야 하기 때문이다.
    렌더가 시작된 뒤에 발견하면 잡이 error 로 떨어져 폴링해야만 알 수 있다.

    groups 는 {그룹명: ReqTimeRanges} — 야구는 innings, 축구는 groups 로 필드명만 다르고 구조는 같다.

      원본 없음   → 404 SOURCE_NOT_FOUND
      영상 아님   → 400 INVALID_VIDEO
      구간 이상   → 400 INVALID_SEGMENT
    """
    video_file = Path(file_path)
    try:
        # ffmpeg 계층은 dto 를 모른다 (미디어만 아는 채로 두려고) — 받는 쪽에서 형변환한다
        media_info = MediaInfo(**ffmpeg.probe(video_file))   # 영상 스트림이 없으면 RuntimeError
    except Exception as e:                      # noqa: BLE001 — ffprobe 실패도 "영상 아님" 으로 환원
        raise err(400, "INVALID_VIDEO", f"원본을 영상으로 읽을 수 없습니다: {video_file.name} ({e})")

    if not groups:
        raise err(400, "INVALID_SEGMENT", "구간이 비어 있습니다")
    for group_name, ranges in groups.items():
        if not ranges:
            raise err(400, "INVALID_SEGMENT", f"'{group_name}' 에 구간이 없습니다")
        for time_range in ranges:
            if time_range.start_sec < 0:
                raise err(400, "INVALID_SEGMENT",
                          f"'{group_name}' start_sec 가 음수입니다: {time_range.start_sec}")
            if time_range.end_sec <= time_range.start_sec:
                raise err(400, "INVALID_SEGMENT",
                          f"'{group_name}' 구간이 올바르지 않습니다: "
                          f"start={time_range.start_sec} end={time_range.end_sec}")
            if time_range.start_sec >= media_info.duration:
                raise err(400, "INVALID_SEGMENT",
                          f"'{group_name}' 구간 시작이 원본 길이를 넘습니다: "
                          f"{util.hms(time_range.start_sec)} > {util.hms(media_info.duration)}")
    return media_info
