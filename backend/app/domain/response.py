"""대응안 후보 만들기 (US-10). 일정 목록만 다루는 순수 함수다.

후보 네 종류 (AC-01). 모두 '경보일까지 나가는 돈' 하나를 골라 언제 낼지만 바꾼다. 금액을 없애는 안은 만들지 않는다.
- PAY_DATE_SHIFT 결제일 조정: 매입처 대금을 뒤의 입금일로 미룬다 (최대 30일).
- PURCHASE_SPLIT 매입 분할: 매입처 대금의 절반만 원래 날에 내고 나머지를 뒤의 입금일에 낸다 (최대 30일).
- EXPENSE_SHIFT 지출 조정: 고정비 하나를 뒤의 입금일로 미룬다 (최대 14일). 인건비·4대보험·세금은 미루지 않는다.
- LOAN_CHECK 상환 일정 점검: 대출 상환을 뒤의 입금일로 옮겨 본다 (최대 14일). 은행과 협의할 일이라 '점검'으로 부른다.

옮길 날짜는 경보일 뒤에 돈이 들어오는 날 중에서 고른다. 그날 들어온 돈으로 낼 수 있어야 의미가 있기 때문이다.
4주 신호가 가장 좋아지는 날을 고른다. 신호가 나아지면 그중 가장 덜 미루는 날을(협의 부담이 작다),
신호가 그대로면 4주 최저 잔액이 가장 높은 날을 고른다.
4주 최저 잔액이 기준안보다 나아지지 않는 후보는 버린다. 효과 계산은 모두 cashflow_engine이 한다.
"""
from dataclasses import dataclass, field
from datetime import date, timedelta

from . import cashflow_engine
from .constants import ALERT_DAYS, HORIZON_DAYS
from .enums import SignalLevel

SIGNAL_RANK = {SignalLevel.RED: 0, SignalLevel.YELLOW: 1, SignalLevel.GREEN: 2}
# 늦게 내면 가산세·연체 처리나 근로기준법 문제가 생기는 지출. 이름으로만 판단하므로 화면에서는 근거와 함께 보여 준다.
NO_DEFER_WORDS = ("인건비", "급여", "월급", "4대보험", "국민연금", "건강보험", "부가세", "세금", "원천세")
MAX_SHIFT = {"PAY_DATE_SHIFT": 30, "PURCHASE_SPLIT": 30, "EXPENSE_SHIFT": 14, "LOAN_CHECK": 14}
TARGET_KIND = {"PAY_DATE_SHIFT": "PURCHASE", "PURCHASE_SPLIT": "PURCHASE", "EXPENSE_SHIFT": "FIXED_COST", "LOAN_CHECK": "LOAN"}
ORDER = list(MAX_SHIFT)


@dataclass(frozen=True)
class Event:
    event_id: int
    due_date: date
    amount: int  # 입금 +, 출금 -
    label: str
    kind: str  # SALES / PURCHASE / FIXED_COST / LOAN
    adjusted: bool = False  # 이미 승인한 대응안으로 옮겨진 일정이면 다시 건드리지 않는다


@dataclass(frozen=True)
class Part:
    due_date: date
    amount: int  # 양수 (출금액)


@dataclass
class Plan:
    kind: str
    target: Event
    parts: list[Part]
    forecast: cashflow_engine.Forecast
    shift_days: int = field(default=0)


@dataclass(frozen=True)
class Setting:
    base_date: date
    start_balance: int
    safety_balance: int


def _forecast(st: Setting, events: list[tuple[date, int]]) -> cashflow_engine.Forecast:
    return cashflow_engine.forecast(st.base_date, st.start_balance, st.safety_balance, events)


def _score(f: cashflow_engine.Forecast) -> tuple[int, int]:
    return SIGNAL_RANK[f.signal], min(b for _, b in f.daily[:ALERT_DAYS])


def trigger_date(f: cashflow_engine.Forecast) -> date | None:
    if f.signal == SignalLevel.RED:
        return f.first_shortage_date
    if f.signal == SignalLevel.YELLOW:
        return f.first_below_safe_date
    return None


def split(amount: int) -> tuple[int, int]:
    """절반을 1만 원 단위로 내려 먼저 내고 나머지를 나중에 낸다."""
    first = amount // 2 // 10_000 * 10_000 or amount // 2
    return first, amount - first


def _parts(kind: str, e: Event, new_date: date) -> list[Part]:
    if kind == "PURCHASE_SPLIT":
        first, rest = split(-e.amount)
        return [Part(e.due_date, first), Part(new_date, rest)]
    return [Part(new_date, -e.amount)]


def _eligible(kind: str, e: Event, st: Setting, trigger: date) -> bool:
    if e.adjusted or e.amount >= 0 or e.kind != TARGET_KIND[kind] or not (st.base_date <= e.due_date <= trigger):
        return False
    if kind == "EXPENSE_SHIFT" and any(w in e.label for w in NO_DEFER_WORDS):
        return False
    return True


def best_plan(kind: str, events: list[Event], st: Setting) -> Plan | None:
    base = _forecast(st, [(e.due_date, e.amount) for e in events])
    trigger = trigger_date(base)
    if trigger is None:
        return None
    end = st.base_date + timedelta(days=HORIZON_DAYS - 1)
    in_days = sorted({e.due_date for e in events if e.amount > 0 and trigger < e.due_date <= end})
    base_sig, base_low = _score(base)
    best: tuple[tuple, Plan] | None = None
    for e in events:
        if not _eligible(kind, e, st, trigger):
            continue
        for d in in_days:
            shift = (d - e.due_date).days
            if shift > MAX_SHIFT[kind]:
                break
            parts = _parts(kind, e, d)
            moved = [(x.due_date, x.amount) for x in events if x.event_id != e.event_id] + [(p.due_date, -p.amount) for p in parts]
            f = _forecast(st, moved)
            sig, low = _score(f)
            key = (sig, -shift, low) if sig > base_sig else (sig, low, -shift)
            if best is None or key > best[0]:
                best = (key, Plan(kind=kind, target=e, parts=parts, forecast=f, shift_days=shift))
    if best is None or _score(best[1].forecast) <= (base_sig, base_low):
        return None  # 신호도 4주 최저 잔액도 나아지지 않으면 후보가 아니다
    return best[1]


def propose(events: list[Event], st: Setting) -> tuple[cashflow_engine.Forecast, list[Plan]]:
    """기준안 계산과 종류별 최선 후보 (효과 큰 순)."""
    base = _forecast(st, [(e.due_date, e.amount) for e in events])
    plans = [p for p in (best_plan(k, events, st) for k in ORDER) if p]
    plans.sort(key=lambda p: (_score(p.forecast), -p.shift_days), reverse=True)
    return base, plans
