"""잡동사니 헬퍼 — 시간 표기."""


def hms(sec: float) -> str:
    """초 → hh:mm:ss.f. 로그 표기용 (요청의 *_hms 는 신뢰하지 않고 sec 에서 다시 만든다)."""
    h, rem = divmod(max(sec, 0.0), 3600)
    m, s = divmod(rem, 60)
    return f"{int(h):02d}:{int(m):02d}:{s:04.1f}"
