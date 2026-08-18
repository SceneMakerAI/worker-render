"""서비스 설정 — .env 로딩.

값 추가는 .env 에 넣고 여기서 한 번 읽어 상수로 노출한다.
"""
from pathlib import Path

import logging
import os
from dotenv import load_dotenv

load_dotenv(override=True)   # .env 가 기존 OS 환경변수를 이기도록 override

# ── 로그
LOG_DIR = "/usr/service/logs/scenemaker/render"
os.makedirs(LOG_DIR, exist_ok=True)   # basicConfig 가 import 시점에 파일을 열므로 디렉토리 먼저 보장
logging.basicConfig(
    format='%(asctime)s %(levelname)s [%(filename)s:%(funcName)s:%(lineno)d] - %(message)s',
    filename=f"{LOG_DIR}/render.log",
    datefmt='%Y/%m/%d %H:%M:%S',
    level=logging.INFO,
)

# ── 서버
HOST = os.getenv("HOST")
PORT = int(os.getenv("PORT"))

# ── ffmpeg 실행 — ffmpeg/ffprobe 가 들어있는 디렉토리
FFMPEG_DIR = Path(os.getenv("FFMPEG_DIR"))
GPU_NUM = int(os.getenv("GPU_NUM"))   # NVDEC/NVENC 가 쓸 GPU 인덱스

# ── 스토리지
INPUT_DATA_DIR = Path(os.getenv("INPUT_DATA_DIR"))     # 입력 원본
OUTPUT_DATA_DIR = Path(os.getenv("OUTPUT_DATA_DIR"))   # 렌더 결과물

# 범퍼(타이틀 카드) 디렉토리 — 종목마다 폴더가 다르다.
# 어떤 파일을 어떤 순서로 쓸지는 각 종목 핸들러가 안다. 여기는 "어디에 있나"만.
BUMPER_DATA_DIR = {
    "baseball": INPUT_DATA_DIR / "baseball",
    "soccer": INPUT_DATA_DIR / "soccer",
}

MAX_THREAD_QUEUE = 5

S3URL = os.getenv("S3URL")

# 렌더가 끝난 뒤 중간 조각(work_{c_id})을 지울지 — 1 삭제, 0 보존.
# 실패는 보존이 기본이다: 어느 조각에서 깨졌는지 봐야 한다. 조각 수십 개면 GB 단위라 오래 두면 안 된다.
DELETE_WORK_DIR = {
    "SUCCESS": 1,
    "ERROR": 0,
}
