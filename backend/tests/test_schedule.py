"""T3·T7: 예정일 생성 규칙 (US-01 AC-01·03, US-02 AC-01·02·04)."""
from datetime import date

from app.domain.enums import PayCycle
from app.domain.schedule import due_dates

BASE = date(2026, 11, 1)


def test_monthly_31_clamps_to_month_end():
    """US-01 AC-03: 결제일 31일은 30일까지 있는 달에 말일로 보정."""
    assert due_dates(PayCycle.MONTHLY, 31, BASE) == [date(2026, 11, 30), date(2026, 12, 31)]  # 1/31은 84일째(1/23) 뒤


def test_monthly_31_in_february():
    assert due_dates(PayCycle.MONTHLY, 31, date(2027, 1, 15))[:2] == [date(2027, 1, 31), date(2027, 2, 28)]


def test_monthly_25_twelve_weeks():
    """US-02 AC-01·02: 매월 25일 임대료·상환 → 12주(11/1~1/23) 안의 25일은 11/25, 12/25 두 번."""
    assert due_dates(PayCycle.MONTHLY, 25, BASE) == [date(2026, 11, 25), date(2026, 12, 25)]


def test_quarterly_only_listed_month_end():
    """US-02 AC-04: 분기 고정비는 해당 월(3·6·9·12월) 말일에만."""
    assert due_dates(PayCycle.QUARTERLY, 31, BASE) == [date(2026, 12, 31)]
    assert due_dates(PayCycle.QUARTERLY, 31, BASE, months=(11, 2)) == [date(2026, 11, 30)]


def test_weekly_friday():
    days = due_dates(PayCycle.WEEKLY, 5, BASE)
    assert days[0] == date(2026, 11, 6) and len(days) == 12 and all(d.weekday() == 4 for d in days)


def test_contract_period_bounds():
    assert due_dates(PayCycle.MONTHLY, 10, BASE, start=date(2026, 12, 1), end=date(2026, 12, 31)) == [date(2026, 12, 10)]
