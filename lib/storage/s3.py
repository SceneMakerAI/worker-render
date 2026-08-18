"""S3 업로드 — 결과물을 config.S3URL 아래로 올린다.

boto3 를 쓰는 이유: 의존성이 uv.lock 에 고정되어 배포마다 같고(호스트에 aws CLI 가 깔려 있어야
하는 문제가 없다), 실패가 ClientError 로 와서 잡 상태에 그대로 담을 수 있다.
전송 자체는 aws CLI 와 같다 — CLI 내부도 boto3 이고 둘 다 멀티파트로 병렬 전송한다.

S3URL 이 비어 있으면 업로드를 건너뛴다 (로컬만 쓰는 환경).
"""
import json
import logging
from pathlib import Path
from urllib.parse import urlparse

import boto3

import config

log = logging.getLogger(__name__)

_client = None


def load():
    """기동 때 **메인 스레드에서** 클라이언트를 만들어 둔다.

    워커 스레드에서 만들면 자격증명 조회 중 SSLContext 생성이 `unknown error (_ssl.c:3123)` 로
    깨진다 (python 3.13 + OpenSSL 3.0, 재현 확인). 만들어 둔 걸 스레드에서 쓰는 건 정상이다 —
    클라이언트는 연결이 아니라 설정 + 커넥션 풀이고, botocore 클라이언트는 생성 후 스레드 안전하다.
    """
    global _client
    if not enabled():
        log.info("S3URL 없음 — 업로드하지 않는다")
        return
    _client = boto3.client("s3")
    bucket, prefix = _bucket_prefix()
    log.info(f"s3 준비 — bucket={bucket} prefix={prefix}")


def _s3():
    if _client is None:
        raise RuntimeError("s3 클라이언트가 없습니다 — 기동 때 s3.load() 가 안 불렸습니다")
    return _client


def _bucket_prefix() -> tuple[str, str]:
    """s3://bucket/prefix → (bucket, prefix). prefix 는 없을 수 있다."""
    parsed = urlparse(config.S3URL)
    return parsed.netloc, parsed.path.strip("/")


def enabled() -> bool:
    """S3URL 이 설정돼 있나."""
    return bool(config.S3URL)


def upload(src: Path, key: str) -> str:
    """src 를 S3URL 아래 key 로 올리고 s3:// 주소를 돌려준다.

    key 는 S3URL 기준 상대 경로 (예: "200/200_1.mp4").
    """
    bucket, prefix = _bucket_prefix()
    full_key = f"{prefix}/{key}" if prefix else key

    size_mb = src.stat().st_size / 2**20
    log.info(f"s3 upload {src.name} ({size_mb:.0f}MB) → s3://{bucket}/{full_key}")
    _s3().upload_file(str(src), bucket, full_key)

    return f"s3://{bucket}/{full_key}"


def upload_json(data, key: str) -> str:
    """data 를 JSON 으로 올린다. 결과물 옆에 두는 사이드카용."""
    bucket, prefix = _bucket_prefix()
    full_key = f"{prefix}/{key}" if prefix else key

    body = json.dumps(data, ensure_ascii=False, indent=2).encode()
    log.info(f"s3 upload {key} ({len(body)}B) → s3://{bucket}/{full_key}")
    _s3().put_object(Bucket=bucket, Key=full_key, Body=body,
                     ContentType="application/json; charset=utf-8")

    return f"s3://{bucket}/{full_key}"
