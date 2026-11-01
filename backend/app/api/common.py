"""여러 라우터가 같이 쓰는 조회 도우미."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain.enums import CashSource
from ..models import CashEvent


def due_dates_of(s: Session, source: CashSource, source_id: int) -> list:
    return list(s.scalars(select(CashEvent.due_date).where(CashEvent.source_type == source, CashEvent.source_id == source_id).order_by(CashEvent.due_date)))
