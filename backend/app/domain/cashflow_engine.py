"""CashflowEngine: 날짜순 원장으로 일별 예상 잔액, 최초 부족일, 신호를 계산한다.

프레임워크·DB·현재 시각·난수를 쓰지 않는 순수 함수다 (양식 6 무결성 규칙 4).
규칙은 tests/fixtures/cashflow/README.md와 같다.
- 구간은 기준일부터 84일, 기준일이 1일째다. 구간 밖 일정은 무시한다.
- 같은 날 입출금은 하루 합계로 반영한다.
- 최초 부족일은 잔액이 처음 0원 미만인 날, 부족액은 그날 잔액의 절댓값이다 (규칙 5).
- 신호는 1~28일째로 판정한다: 0원 미만 RED, 안전 잔액 미만 YELLOW, 그 외 GREEN (규칙 6).
"""
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable

from .enums import SignalLevel

HORIZON_DAYS = 84
ALERT_DAYS = 28


@dataclass(frozen=True)
class Forecast:
    daily: list[tuple[date, int]]
    first_shortage_date: date | None
    shortage_amount: int | None
    max_shortage_amount: int | None
    min_balance: int
    min_balance_date: date
    signal: SignalLevel
    first_below_safe_date: date | None


def forecast(base_date: date, start_balance: int, safe_balance: int, events: Iterable[tuple[date, int]]) -> Forecast:
    """events: (날짜, 금액) 목록. 입금은 +, 출금은 -."""
    net: dict[int, int] = defaultdict(int)
    for day, amount in events:
        offset = (day - base_date).days
        if 0 <= offset < HORIZON_DAYS:
            net[offset] += amount

    daily: list[tuple[date, int]] = []
    balance = start_balance
    for i in range(HORIZON_DAYS):
        balance += net[i]
        daily.append((base_date + timedelta(days=i), balance))

    short = next(((d, -b) for d, b in daily if b < 0), None)
    min_date, min_balance = min(daily, key=lambda x: x[1])
    window = daily[:ALERT_DAYS]
    if any(b < 0 for _, b in window):
        signal = SignalLevel.RED
    elif any(b < safe_balance for _, b in window):
        signal = SignalLevel.YELLOW
    else:
        signal = SignalLevel.GREEN
    below_safe = next((d for d, b in window if b < safe_balance), None)

    return Forecast(
        daily=daily,
        first_shortage_date=short[0] if short else None,
        shortage_amount=short[1] if short else None,
        max_shortage_amount=-min_balance if min_balance < 0 else None,
        min_balance=min_balance,
        min_balance_date=min_date,
        signal=signal,
        first_below_safe_date=below_safe,
    )
