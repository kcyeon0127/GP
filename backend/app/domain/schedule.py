"""결제 조건·고정비·대출 상환에서 12주 예정일을 만드는 순수 함수 (US-01·02, 무결성 규칙 3).

- MONTHLY: 매월 pay_day. 그 달에 그날이 없으면 말일로 당긴다 (31일 → 11/30).
- QUARTERLY: months(기본 3·6·9·12월)에만 pay_day. 말일 보정은 같다.
- WEEKLY: pay_day는 요일 번호(1=월요일 … 7=일요일).
"""
import calendar
from datetime import date, timedelta

from .cashflow_engine import HORIZON_DAYS
from .enums import PayCycle

DEFAULT_QUARTER_MONTHS = (3, 6, 9, 12)


def clamp_day(year: int, month: int, day: int) -> date:
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def due_dates(cycle: PayCycle, pay_day: int, base_date: date, months: tuple[int, ...] | None = None,
              start: date | None = None, end: date | None = None) -> list[date]:
    last = base_date + timedelta(days=HORIZON_DAYS - 1)
    lo = max(base_date, start) if start else base_date
    hi = min(last, end) if end else last
    out: list[date] = []
    if cycle == PayCycle.WEEKLY:
        d = lo + timedelta(days=(pay_day - 1 - lo.weekday()) % 7)
        while d <= hi:
            out.append(d)
            d += timedelta(days=7)
        return out
    allowed = set(months or DEFAULT_QUARTER_MONTHS) if cycle == PayCycle.QUARTERLY else None
    y, m = lo.year, lo.month
    while date(y, m, 1) <= hi:
        if allowed is None or m in allowed:
            d = clamp_day(y, m, pay_day)
            if lo <= d <= hi:
                out.append(d)
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def parse_months(text: str | None) -> tuple[int, ...] | None:
    if not text:
        return None
    return tuple(int(x) for x in text.replace(" ", "").split(",") if x)
