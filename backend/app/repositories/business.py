import os
from datetime import date

from sqlalchemy.orm import Session

from ..models import Business

DEFAULT_BUSINESS_ID = int(os.getenv("BUSINESS_ID", "1"))


def get_or_create(s: Session) -> Business:
    """단일 사업장 MVP: 사업장 1번을 쓴다. 없으면 기본값으로 만든다."""
    b = s.get(Business, DEFAULT_BUSINESS_ID)
    if b is None:
        b = Business(business_id=DEFAULT_BUSINESS_ID, name="내 사업장", current_balance=0, safety_balance=1_000_000, base_date=date.today())
        s.add(b)
        s.flush()
    return b
