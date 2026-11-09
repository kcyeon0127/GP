"""US-10·12: 대응안 요청·비교·승인과 협의 메시지 초안. 제시만으로는 일정이 바뀌지 않고, 승인해야 예상 잔액에 반영된다."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import Business
from ..services import response_service as svc
from .deps import business
from .forecasts import _out

router = APIRouter(prefix="/api")


@router.post("/response-plans", status_code=201)
def request_plans(s: Session = Depends(get_session), b: Business = Depends(business)):
    out = svc.propose(s, b)
    s.commit()
    return out


@router.get("/response-plans/approved")
def approved_plans(s: Session = Depends(get_session), b: Business = Depends(business)):
    return svc.approved(s, b)


def _decide(action, plan_id: int, s: Session, b: Business) -> dict:
    p = svc._get(s, b, plan_id)
    if p is None:
        raise HTTPException(404, detail="대응안이 없습니다")
    try:
        r = action(s, b, p)
    except svc.PlanConflict as e:
        raise HTTPException(409, detail=str(e))
    s.commit()
    return {"plan": svc._dto(p), "forecast": _out(s, r, with_daily=True)}


@router.post("/response-plans/{plan_id}/approve")
def approve_plan(plan_id: int, s: Session = Depends(get_session), b: Business = Depends(business)):
    return _decide(svc.approve, plan_id, s, b)


@router.post("/response-plans/{plan_id}/cancel")
def cancel_plan(plan_id: int, s: Session = Depends(get_session), b: Business = Depends(business)):
    return _decide(svc.cancel, plan_id, s, b)


@router.post("/response-plans/{plan_id}/draft")
def draft_message(plan_id: int, s: Session = Depends(get_session), b: Business = Depends(business)):
    """승인한 대응안의 협의 메시지 초안. 보내지는 않는다: 사장님이 복사해서 직접 보낸다 (US-12 AC-02)."""
    p = svc._get(s, b, plan_id)
    if p is None:
        raise HTTPException(404, detail="대응안이 없습니다")
    try:
        return svc.draft(s, b, p)
    except svc.PlanConflict as e:
        raise HTTPException(409, detail=str(e))
