"""US-03~05·07: 예상 잔액(T11), 경보(T17), 근거(T26) API."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import Business, CashEvent, ForecastRun
from ..schemas import DailyBalance, ForecastIn, ForecastOut
from ..services import evidence_service, forecast_service
from .deps import business

router = APIRouter(prefix="/api")


def _out(s: Session, r: ForecastRun, with_daily: bool) -> ForecastOut:
    has_events = bool(s.scalar(select(func.count()).select_from(CashEvent).where(CashEvent.business_id == r.business_id)))
    if not has_events:
        msg = "등록된 입출금 일정이 없습니다. 거래처·고정비·대출 일정을 등록하세요."
    elif r.first_shortage_date:
        msg = f"{r.first_shortage_date:%m/%d}에 {r.shortage_amount:,}원 부족 예상"
    else:
        msg = "부족 예상 없음"
    daily = [DailyBalance(date=d.date, balance=d.balance) for d in forecast_service.daily(s, r.run_id)] if with_daily else None
    return ForecastOut(run_id=r.run_id, base_date=r.base_date, start_balance=r.start_balance, safety_balance=r.safety_balance, signal=r.signal.value,
                       first_shortage_date=r.first_shortage_date, shortage_amount=r.shortage_amount, max_shortage_amount=r.max_shortage_amount,
                       min_balance=r.min_balance, min_balance_date=r.min_balance_date, first_below_safe_date=r.first_below_safe_date,
                       has_events=has_events, message=msg, daily=daily)


def _run(s: Session, run_id: int, b: Business) -> ForecastRun:
    r = s.get(ForecastRun, run_id)
    if not r or r.business_id != b.business_id:
        raise HTTPException(404, detail="계산 결과가 없습니다")
    return r


@router.post("/forecasts", response_model=ForecastOut, status_code=201)
def create_forecast(body: ForecastIn, s: Session = Depends(get_session), b: Business = Depends(business)):
    r = forecast_service.run(s, b, body.base_date, body.current_balance, body.safety_balance)
    s.commit()
    return _out(s, r, with_daily=True)


@router.get("/forecasts/{run_id}/daily", response_model=list[DailyBalance])
def forecast_daily(run_id: int, s: Session = Depends(get_session), b: Business = Depends(business)):
    _run(s, run_id, b)
    return [DailyBalance(date=d.date, balance=d.balance) for d in forecast_service.daily(s, run_id)]


@router.get("/alerts/current", response_model=ForecastOut)
def current_alert(s: Session = Depends(get_session), b: Business = Depends(business)):
    r = forecast_service.latest(s, b.business_id)
    if r is None:
        r = forecast_service.run(s, b)
        s.commit()
    return _out(s, r, with_daily=False)


@router.get("/alerts/{run_id}/drivers")
def alert_drivers(run_id: int, s: Session = Depends(get_session), b: Business = Depends(business)):
    r = _run(s, run_id, b)
    t = forecast_service.trigger_date(r)
    return {"run_id": run_id, "signal": r.signal.value, "trigger_date": t,
            "drivers": [dict(cash_event_id=e.cash_event_id, date=e.due_date, label=e.label, direction=e.direction.value, amount=e.amount, role=role)
                        for e, role in forecast_service.drivers(s, r)]}


@router.get("/alerts/{run_id}/evidence")
def alert_evidence(run_id: int, s: Session = Depends(get_session), b: Business = Depends(business)):
    r = _run(s, run_id, b)
    out = evidence_service.collect(s, r)
    s.commit()
    return out
