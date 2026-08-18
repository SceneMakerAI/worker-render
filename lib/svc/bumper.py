"""범퍼(타이틀 카드) — 기동 때 한 번 확인해 메모리에 들고 있는다.

정적 파일이라 요청마다 디스크를 뒤질 이유가 없다. 여기서 걸러두면 렌더 도중에 파일 문제로
깨지지 않는다. 대신 파일을 바꾸면 재기동해야 반영된다.
"""
import logging
from pathlib import Path

import config
from lib.dto import MediaInfo
from lib.media import ffmpeg

log = logging.getLogger(__name__)

# 어떤 파일을 쓸지는 종목 규칙이다. 야구는 {이닝}_{top|bot}, 연장 15회까지.
FILES: dict[str, dict[str, Path]] = {
    "baseball": {f"{inning}_{half}":
                 config.BUMPER_DATA_DIR["baseball"] / f"inning_bumper_{inning:02d}_{half}.mp4"
                 for inning in range(1, 16)
                 for half in ("top", "bot")},
    # soccer 는 규격 미정
}

INFO: dict[str, dict[str, MediaInfo]] = {}      # 기동 때 채운다 — 실제로 읽히는 것만


def load():
    """범퍼를 probe 해서 INFO 에 올린다. 없거나 영상으로 못 읽는 건 뺀다."""
    INFO.clear()
    for sport, files in FILES.items():
        info, missing, broken = {}, [], []
        for key, path in files.items():
            if not path.exists():
                missing.append(key)
                continue
            try:
                info[key] = MediaInfo(**ffmpeg.probe(path))
            except Exception as e:              # noqa: BLE001 — 못 읽는 건 없는 셈 친다
                broken.append(f"{key}({e})")
        INFO[sport] = info

        log.info(f"bumper[{sport}] {len(info)}/{len(files)} 적재 — {config.BUMPER_DATA_DIR[sport]}")
        if missing:
            log.info(f"bumper[{sport}] 없음 {len(missing)}개: {', '.join(missing)}")
        if broken:
            log.warning(f"bumper[{sport}] 읽기 실패 {len(broken)}개: {', '.join(broken)}")

        silent = [k for k, i in info.items() if not i.has_audio]
        if silent:
            log.warning(f"bumper[{sport}] 무음 {len(silent)}개: {', '.join(silent)}")


def paths(sport: str) -> dict[str, Path]:
    """쓸 수 있는 범퍼만 {키: 경로}. compose 에 그대로 넘긴다."""
    return {key: FILES[sport][key] for key in INFO.get(sport, {})}
