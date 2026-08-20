"""POST /render/sports/baseball — 야구 하이라이트 렌더 접수.

이닝 그룹 순서대로 구간을 이어붙이고, 각 이닝 앞에 해당 이닝의 범퍼(타이틀 카드)를 붙인다.

sync_yn=False  접수만 하고 accepted 를 즉시 반환. 실제 렌더는 job 워커 스레드에서 진행되고
               결과는 GET /render/{v_id}/{c_id} 로 폴링한다.
sync_yn=True   렌더가 끝날 때까지 붙잡고 있다가 done/error 를 반환. 구간이 많으면 수 분 걸린다.

어느 쪽이든 ffmpeg 은 서버 전체에서 한 번에 하나만 돈다 (job 워커 1개).

문법 검증(타입·필수 필드)은 pydantic + 앱 레벨 핸들러가 처리하고,
파일·구간이 실제로 쓸 수 있는지는 여기서 확인한 뒤 svc 로 넘긴다 —
스레드가 뜨기 전에 실패할 수 있는 건 전부 여기서 걸러낸다.
"""
import logging

from fastapi import APIRouter
from pydantic import BaseModel

from lib.dto import ReqTimeRanges, ResRender
from lib.http.http_util import download_video, check_video_format, err, log_req, log_res
from lib.svc import bumper, compose
from lib.svc import render as render_svc

router = APIRouter(prefix="/render/sports", tags=["render"])
log = logging.getLogger(__name__)



class BaseballRequest(BaseModel):
    v_id: int                            # 영상 ID
    c_id: int                            # 하이라이트 편성 ID (agent compose 생성)
    sync_yn: bool = True
    bumper_yn: bool = False                  # 이닝 범퍼 삽입 여부
    innings: dict[str, ReqTimeRanges]    # 키 = {이닝번호}_{top|bot} (예: 1_top, 5_bot)


@router.post("/baseball", response_model=ResRender)
def baseball(req: BaseballRequest):
    log_req(req)

    # 검사 — 모든 입력이 문제 없는지. 여기서 걸리면 잡을 만들지 않고 404/400 으로 끝낸다
    local_file = download_video(req.v_id)
    media_info = check_video_format(local_file, req.innings)


    # 조립 — 이닝 편성 → 조각 목록. 어떤 ㅊ 쓸지는 야구만 아는 규칙이라 여기서 넘긴다
    parts = compose.to_media_parts(local_file, req.innings,
                                   bumper.paths("baseball") if req.bumper_yn else None)

    # thread 호출 — sync_yn=false 면 accepted 로 즉시, true 면 렌더가 끝난 뒤 done/error 로 돌아온다
    try:
        res = render_svc.start(req.v_id, req.c_id, parts, media_info, sync=req.sync_yn)
    except render_svc.QueueFull as e:
        raise err(429, "TOO_MANY_JOBS", str(e))

    log_res(res)
    return res
