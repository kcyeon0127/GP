"""거래 패턴으로 결제조건 추정 (US-14 T1). DB 없이 거래 목록만 다루는 순수 함수다.

매출처(입금)마다 실제 입금 날짜를 보고 결제 주기·결제일·평균 지연일을 추정한다.
- 거래 3건 미만이면 추정하지 않는다 (INSUFFICIENT). 2건으로는 주기와 지연을 구분할 수 없다.
- 주기: 입금 간격 중앙값이 6~8일이면 매주, 25~35일이면 매월. 그 밖이면 불규칙 (IRREGULAR).
- 등록된 거래처: 등록 결제일을 약속일로 보고, 입금일 - 약속일을 지연일로 잰다.
- 등록 안 된 거래처: 약속일을 알 수 없어, 입금일 중 앞쪽 25% 지점을 결제일로 보고 그보다 늦은 만큼을 지연으로 본다.
  (한두 번 일찍 들어온 날에 끌려가지 않게 최솟값 대신 하위 25%를 쓴다)
- 지연일 평균은 0일 이상만 센다: 약속보다 일찍 들어온 날은 부족 위험을 만들지 않는다.
추정값은 대표자가 확정하기 전까지 "추정"이다. 확정한 지연일만 예측(US-15)에 쓴다.
"""
import statistics
from dataclasses import dataclass, field, replace
from datetime import date, timedelta

from .schedule import clamp_day
from .transactions import Txn, _name_key, canonical

MIN_TXNS = 3
EARLY_SLACK = 10  # 약속일보다 이만큼 이르면 이전 달 약속분이 아니라 이번 달 약속분이 일찍 온 것으로 본다


@dataclass(frozen=True)
class Registered:
    counterparty_id: int
    name: str
    pay_cycle: str  # WEEKLY / MONTHLY / QUARTERLY
    pay_day: int


@dataclass
class Estimate:
    name: str
    status: str  # ESTIMATED / INSUFFICIENT / IRREGULAR
    count: int
    dates: list[date] = field(default_factory=list)
    amount: int = 0
    counterparty_id: int | None = None
    registered_cycle: str | None = None
    registered_day: int | None = None
    pay_cycle: str | None = None
    pay_day: int | None = None
    avg_delay_days: int | None = None
    max_delay_days: int | None = None
    delays: list[int] = field(default_factory=list)
    basis: str = ""  # 화면에 보여 줄 추정 근거 한 줄


def _promised_monthly(actual: date, day: int) -> date:
    """이 입금이 어느 달 약속분인지: 이번 달 약속일이 EARLY_SLACK일 넘게 뒤면 이번 달 것이 일찍 온 것, 아니면 가장 가까운 지난 약속일."""
    this = clamp_day(actual.year, actual.month, day)
    if actual >= this or (this - actual).days <= EARLY_SLACK:
        return this
    y, m = (actual.year - 1, 12) if actual.month == 1 else (actual.year, actual.month - 1)
    return clamp_day(y, m, day)


def _promised_weekly(actual: date, weekday: int) -> date:
    """가장 가까운 지난 약속 요일 (같은 요일이면 그날)."""
    return actual - timedelta(days=(actual.isoweekday() - weekday) % 7)


def _cycle(days: list[date]) -> str | None:
    gaps = [(b - a).days for a, b in zip(days, days[1:])]
    g = statistics.median(gaps)
    if 6 <= g <= 8:
        return "WEEKLY"
    if 25 <= g <= 35:
        return "MONTHLY"
    return None


def estimate(txns: list[Txn], registered: list[Registered] = (), merges: dict[str, str] | None = None) -> list[Estimate]:
    merges = merges or {}
    reg = {canonical(r.name): r for r in registered}
    groups: dict[str, list[Txn]] = {}
    for t in txns:
        if t.amount <= 0:
            continue
        k = _name_key(t.desc)
        k = merges.get(k, k)
        if k:
            groups.setdefault(k, []).append(t)
    out: list[Estimate] = []
    for name, ts in groups.items():
        r = reg.get(canonical(name))
        days = sorted(t.day for t in ts)
        e = Estimate(name=r.name if r else name, status="INSUFFICIENT", count=len(ts), dates=days,
                     amount=int(statistics.median(t.amount for t in ts)), counterparty_id=r.counterparty_id if r else None,
                     registered_cycle=r.pay_cycle if r else None, registered_day=r.pay_day if r else None)
        if len(ts) < MIN_TXNS:
            e.basis = f"입금 {len(ts)}건이라 추정하지 않았어요 ({MIN_TXNS}건 이상 필요)"
            out.append(e)
            continue
        gaps = [(b - a).days for a, b in zip(days, days[1:])]
        if statistics.median(gaps) < 6 and not r:
            continue  # 카드매출처럼 매일 들어오는 돈은 결제조건이 있는 거래처가 아니다
        cycle = r.pay_cycle if r and r.pay_cycle in ("WEEKLY", "MONTHLY") else _cycle(days)
        if cycle is None:
            e.status, e.basis = "IRREGULAR", "입금 간격이 매주·매월로 일정하지 않아요"
            out.append(e)
            continue
        if r and r.pay_cycle == cycle:
            day, src = r.pay_day, "등록한 결제일"
        elif cycle == "WEEKLY":
            day, src = statistics.mode(d.isoweekday() for d in days), "가장 많이 들어온 요일을 결제일로 추정"
        else:
            day, src = sorted(d.day for d in days)[len(days) // 4], "이른 입금일 쪽을 결제일로 추정"
        when = f"매주 {'월화수목금토일'[day - 1]}요일" if cycle == "WEEKLY" else f"매월 {day}일"
        promised = [_promised_weekly(d, day) if cycle == "WEEKLY" else _promised_monthly(d, day) for d in days]
        delays = [(d - p).days for d, p in zip(days, promised)]
        late = [max(0, x) for x in delays]
        e.status, e.pay_cycle, e.pay_day, e.delays = "ESTIMATED", cycle, day, delays
        e.avg_delay_days = round(statistics.mean(late))
        e.max_delay_days = max(late)
        e.basis = f"입금 {len(ts)}건, {when}({src})보다 평균 {e.avg_delay_days}일·최대 {e.max_delay_days}일 늦게 들어왔어요"
        out.append(e)
    order = {"ESTIMATED": 0, "IRREGULAR": 1, "INSUFFICIENT": 2}
    return sorted(out, key=lambda x: (order[x.status], x.counterparty_id is None, -x.amount))


def apply_delays(items: list, delays: dict[int, int]) -> list:
    """US-15 T5: 확정한 지연일만큼 그 매출처 입금을 뒤로 민다 (scenario.Item 목록, 원본은 그대로).

    지연 이력이 없는 거래처(delays에 없거나 0일)는 그대로라, 확정값이 없으면 기본 예측과 같다 (T7).
    """
    return [replace(i, due_date=i.due_date + timedelta(days=delays[i.party_id])) if i.kind == "SALES" and delays.get(i.party_id) else i for i in items]
