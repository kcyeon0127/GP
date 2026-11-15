"""US-15 입금 지연 반영 예측 (T5): 확정한 거래처별 지연일을 더한 보수 예측.

기본 예측(홈 경보)은 그대로 두고, 보수 예측은 저장하지 않는 비교용 곡선이다. 추정만 하고 확정하지 않은 값은 쓰지 않는다 (US-14).
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain import cashflow_engine
from ..domain import payment_terms as pt
from ..models import Business, ConfirmedTerm
from .scenario_service import _summary, items_of


def conservative(s: Session, b: Business) -> dict:
    delays = {t.counterparty_id: t.delay_days for t in s.scalars(select(ConfirmedTerm).where(ConfirmedTerm.business_id == b.business_id)) if t.delay_days}
    items = items_of(s, b)
    shifted = pt.apply_delays(items, delays)
    f = cashflow_engine.forecast(b.base_date, b.current_balance, b.safety_balance, [(i.due_date, i.amount) for i in shifted])
    moved = sorted({i.label for i, a in zip(items, shifted) if i.due_date != a.due_date})
    return {**_summary(f), "applied": len(delays), "delays": delays, "moved": moved}
