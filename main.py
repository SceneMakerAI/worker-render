"""app 생성 + 라우터 등록만. 실제 로직은 lib/ 아래 계층에 둠:
    lib/http          핸들러(라우터) + 요청/응답 DTO   전송 계층 (HTTP)
    lib/svc           비즈니스 로직 (transport 무관) — compose / render / bumper
    lib/media         ffmpeg/ffprobe 실행
    lib/dto.py        계층 공통 dataclass
    lib/util.py       잡동사니 헬퍼 (시간 표기)

실행:
    uv run uvicorn main:app --host 0.0.0.0 --port 19700 --reload
"""
import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

import config

from lib.http import http_util, status
from lib.http.sports import baseball, soccer
from lib.storage import s3
from lib.svc import bumper


@asynccontextmanager
async def lifespan(app: FastAPI):
    """기동 때 한 번 — 범퍼를 메모리에 올리고 S3 클라이언트를 만든다.

    둘 다 메인 스레드여야 한다. S3 클라이언트는 워커 스레드에서 만들면 SSL 초기화가 깨진다
    (lib/storage/s3.py 참고).
    """
    bumper.load()
    s3.load()
    yield


app = FastAPI(title="render", version="0.1.0", lifespan=lifespan)

app.include_router(baseball.router)
app.include_router(soccer.router)
app.include_router(status.router)   # /render/{v_id}/{c_id} — 경로 변수라 종목 라우터 뒤에 등록

http_util.register(app)


@app.get("/")
def root():
    return {"message": "hello world", "service": "render"}


if __name__ == "__main__":
    logging.info(f"host={config.HOST}:{config.PORT}")
    uvicorn.run(app, host=config.HOST, port=config.PORT)
