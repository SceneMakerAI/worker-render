"""POST /render/sports/soccer — 축구 하이라이트 렌더 (미구현).

⚠ 요청 스펙(구간 키 규칙, 범퍼 유무) 미확정이라 자리만 잡아 둔다. 지금 부르면 501.

구현할 때는 야구와 같은 3단이면 된다 — 종목이 갈리는 건 "그룹을 어떻게 세우는가" 뿐이고,
조각 목록(list[ReqTimeRange])이 되고 나면 아래는 전부 공통이다:

    media_info = check_video(src, req.groups)
    parts      = compose.to_media_parts(src, req.groups, bumper.paths("soccer") if ... else None)
    out        = render_svc.start(req.v_id, req.c_id, parts, media_info, sync=req.sync_yn)
"""
import logging

from fastapi import APIRouter
from pydantic import BaseModel

from lib.dto import ReqTimeRanges, ResRender
from lib.http.http_util import err, log_req

router = APIRouter(prefix="/render/sports", tags=["render"])
log = logging.getLogger(__name__)


class SoccerRequest(BaseModel):
    v_id: int
    c_id: int
    file_name: str
    sync_yn: bool = True
    bumper_yn: bool = False              # 축구 범퍼 규격 미정 — 기본 off
    groups: dict[str, ReqTimeRanges]     # ⚠ 키 형식 미확정 (예: 1_half)


@router.post("/soccer", response_model=ResRender)
def soccer(req: SoccerRequest):
    log_req(req)
    raise err(501, "NOT_IMPLEMENTED", "축구 렌더는 아직 지원하지 않습니다 (요청 스펙 미확정)")
