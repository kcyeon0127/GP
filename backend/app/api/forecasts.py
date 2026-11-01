"""US-03·04: 12주 예상 잔액 계산과 조회 (T11). 최초 부족일·부족액(T13)은 같은 응답에 담긴다."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import Business, CashEvent, ForecastRun
from ..schemas import DailyBalance, ForecastIn, ForecastOut
from ..services import forecast_service
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
