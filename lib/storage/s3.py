"""S3 업로드 — 결과물을 config.S3URL 아래로 올린다.

boto3 를 쓰는 이유: 의존성이 uv.lock 에 고정되어 배포마다 같고(호스트에 aws CLI 가 깔려 있어야
하는 문제가 없다), 실패가 ClientError 로 와서 잡 상태에 그대로 담을 수 있다.
전송 자체는 aws CLI 와 같다 — CLI 내부도 boto3 이고 둘 다 멀티파트로 병렬 전송한다.

S3URL 이 비어 있으면 업로드를 건너뛴다 (로컬만 쓰는 환경).
"""
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
    log.info(f"s3 준비 — {', '.join(config.S3URL)}")


def _s3():
    if _client is None:
        raise RuntimeError("s3 클라이언트가 없습니다 — 기동 때 s3.load() 가 안 불렸습니다")
    return _client


def _bucket_key(s3_url: str) -> tuple[str, str]:
    """s3://bucket/a/b.mp4 → ("bucket", "a/b.mp4")."""
    parsed = urlparse(s3_url)
    return parsed.netloc, parsed.path.lstrip("/")


def enabled() -> bool:
    """S3URL 이 설정돼 있나."""
    return bool(config.S3URL)


def download_file(s3_url: str, dst: Path) -> Path:
    """s3_url 을 dst 로 받는다. 이미 같은 파일이 있으면 건너뛴다.

    받은 주소를 그대로 쓴다 — 어느 버킷의 어느 키인지, 로컬 어디에 둘지는 부르는 쪽이 정한다.
        s3_url  "s3://bucket/vod/1/201.mp4"
        dst     "/mnt/nvme/vod/1/201.mp4"

    `aws s3 sync` 처럼 **크기가 같으면 받지 않는다.** 원본은 수십 GB 라 재요청마다 다시 받으면
    수 분씩 낭비된다. 크기만 보는 이유는 ETag 가 멀티파트 업로드에서는 MD5 가 아니라
    조각 수에 따라 달라져서, 로컬 파일과 곧바로 비교할 수 없기 때문이다.

    S3 에 없으면 ClientError(404) 가 그대로 올라간다 — 부르는 쪽이 "원본 없음"으로 옮긴다.
    """
    bucket, key = _bucket_key(s3_url)

    remote_size = _s3().head_object(Bucket=bucket, Key=key)["ContentLength"]
    if dst.exists() and dst.stat().st_size == remote_size:
        log.info(f"s3 download 건너뜀 (크기 같음 {remote_size / 2**20:.0f}MB) — {dst}")
        return dst

    dst.parent.mkdir(parents=True, exist_ok=True)
    log.info(f"s3 download {s3_url} ({remote_size / 2**20:.0f}MB) → {dst}")

    # 받다 끊기면 반쪽 파일이 남아 다음 요청이 "있다"고 착각한다. 임시 이름으로 받고 다 되면 옮긴다.
    tmp = dst.with_name(dst.name + ".part")
    _s3().download_file(bucket, key, str(tmp))
    tmp.replace(dst)

    return dst


def upload_file(src: Path, s3_url: str) -> str:
    """src 를 s3_url 로 올린다. download 와 짝 — 주소 조립은 부르는 쪽이 한다.

        src     "/mnt/nvme/vod/output/201/201_1.mp4"
        s3_url  "s3://bucket/result/201/201_1.mp4"
    """
    bucket, key = _bucket_key(s3_url)

    size_mb = src.stat().st_size / 2**20
    log.info(f"s3 upload {src.name} ({size_mb:.0f}MB) → {s3_url}")
    _s3().upload_file(str(src), bucket, key)

    return s3_url
