"""ForecastService(T11)·AlertService(T16·T17): 엔진을 실행하고 결과를 저장·판정한다."""
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain import cashflow_engine
from ..domain.constants import ALERT_DAYS
from ..domain.enums import CashDirection, SignalLevel
from ..models import Business, CashEvent, ForecastDaily, ForecastRun
from . import schedule_service


def events_of(s: Session, business_id: int) -> list[CashEvent]:
    return list(s.scalars(select(CashEvent).where(CashEvent.business_id == business_id).order_by(CashEvent.due_date, CashEvent.cash_event_id)))


def run(s: Session, b: Business, base_date: date | None = None, current_balance: int | None = None, safety_balance: int | None = None) -> ForecastRun:
    changed = base_date is not None and base_date != b.base_date
    if base_date is not None:
        b.base_date = base_date
    if current_balance is not None:
        b.current_balance = current_balance
    if safety_balance is not None:
        b.safety_balance = safety_balance
    if changed:
        schedule_service.regenerate_all(s, b)
    events = events_of(s, b.business_id)
    f = cashflow_engine.forecast(b.base_date, b.current_balance, b.safety_balance, [(e.due_date, e.signed) for e in events])
    r = ForecastRun(business_id=b.business_id, base_date=b.base_date, start_balance=b.current_balance, safety_balance=b.safety_balance,
                    first_shortage_date=f.first_shortage_date, shortage_amount=f.shortage_amount, max_shortage_amount=f.max_shortage_amount,
                    min_balance=f.min_balance, min_balance_date=f.min_balance_date, first_below_safe_date=f.first_below_safe_date, signal=f.signal)
    s.add(r)
    s.flush()
    s.add_all([ForecastDaily(run_id=r.run_id, date=d, balance=bal) for d, bal in f.daily])
    s.flush()
    return r


def daily(s: Session, run_id: int) -> list[ForecastDaily]:
    return list(s.scalars(select(ForecastDaily).where(ForecastDaily.run_id == run_id).order_by(ForecastDaily.date)))


def latest(s: Session, business_id: int) -> ForecastRun | None:
    return s.scalars(select(ForecastRun).where(ForecastRun.business_id == business_id, ForecastRun.scenario_id.is_(None))
                     .order_by(ForecastRun.run_id.desc()).limit(1)).first()


def trigger_date(r: ForecastRun) -> date | None:
    """경보를 일으킨 날: 빨강은 최초 부족일, 노랑은 처음 안전 잔액 미만인 날."""
    if r.signal == SignalLevel.RED:
        return r.first_shortage_date
    if r.signal == SignalLevel.YELLOW:
        return r.first_below_safe_date
    return None


def drivers(s: Session, r: ForecastRun) -> list[tuple[CashEvent, str]]:
    """부족에 영향을 준 일정 (US-05 AC-04).

    - BEFORE: 경보일까지 나간 돈 (금액 큰 순)
    - AFTER: 경보일 뒤 4주 구간 안에 들어올 돈. 더 일찍 들어왔다면 부족을 막았을 입금이다.
    """
    t = trigger_date(r)
    if t is None:
        return []
    window_end = r.base_date.toordinal() + ALERT_DAYS - 1
    evs = [e for e in events_of(s, r.business_id) if r.base_date <= e.due_date]
    before = sorted((e for e in evs if e.due_date <= t and e.direction == CashDirection.OUT), key=lambda e: (-e.amount, e.due_date))
    after = [e for e in evs if t < e.due_date and e.due_date.toordinal() <= window_end and e.direction == CashDirection.IN]
    return [(e, "BEFORE") for e in before] + [(e, "AFTER") for e in after]
