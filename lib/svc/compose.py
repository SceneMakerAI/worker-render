# 그룹({이닝: [시간구간]})을 평탄한 파트 리스트로 바꾸고,
# 그룹마다 범퍼를 앞에 끼운다.
# 범퍼는 start_sec == end_sec == 0 인 ReqTimeRange('파일 전체')로 삽입된다.
# 이 지점 아래에서는 '범퍼'라는 개념이 사라지고, 렌더러는 균일한 파트 목록만 본다.

"""편성 → 이어붙일 조각 목록. 종목 규칙이 여기서 끝난다.

핸들러가 받은 {그룹명: 구간들} 을 렌더가 쓸 평평한 목록으로 편다. 아래 계층은 "이 파일의
이 구간" 만 순서대로 보므로, 이닝·하프·범퍼 같은 개념은 여기서 사라진다.

범퍼는 start/end 가 둘 다 0 인 구간(= 파일 전체)으로 목록에 섞여 들어간다. 렌더 입장에선
다른 조각과 구별되지 않는다. 범퍼를 안 쓰면 애초에 목록에 안 들어간다.
"""
from pathlib import Path

from lib.dto import ReqTimeRange, ReqTimeRanges


def to_media_parts(src: Path, groups: dict[str, ReqTimeRanges],
                   bumpers: dict[str, Path] | None = None) -> list[ReqTimeRange]:
    """{그룹명: 구간들} → [구간, ...] 로 펴고 src 를 채운다.

    bumpers 를 주면 각 그룹 맨 앞에 그 그룹의 카드를 끼운다 (없는 파일은 건너뛴다).
    dict 는 삽입 순서를 유지하므로 요청에 온 순서 그대로다 (편성 순서는 agent 가 정한 것).
    """
    parts: list[ReqTimeRange] = []
    for group_name, ranges in groups.items():
        card = (bumpers or {}).get(group_name)
        if card and card.exists():
            parts.append(ReqTimeRange(src=card, start_sec=0, end_sec=0))    # 0~0 = 파일 전체
        for time_range in ranges:
            parts.append(time_range.model_copy(update={"src": src}))
    return parts
