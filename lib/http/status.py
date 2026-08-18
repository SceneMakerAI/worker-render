"""GET /render/{v_id}/{c_id} — 렌더 상태·결과 조회.

메모리에 잡이 있으면 그 상태를, 없으면 결과 파일 존재로 done 을 판정한다.
둘 다 없으면 404 JOB_NOT_FOUND.
"""
import logging

from fastapi import APIRouter

from lib.dto import ResRender
from lib.http.http_util import err
from lib.svc import render as render_svc

router = APIRouter(prefix="/render", tags=["render"])
log = logging.getLogger(__name__)


@router.get("/{v_id}/{c_id}", response_model=ResRender)
def status(v_id: int, c_id: int):
    res = render_svc.status(v_id, c_id)
    if res is None:
        raise err(404, "JOB_NOT_FOUND", "접수된 렌더링이 없습니다.")
    return res
