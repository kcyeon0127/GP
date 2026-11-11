"""강건성 테스트용 가게 거래내역 생성기 (US-16). 정확도 근거가 아니라 "조건이 나빠질 때 어디까지 버티는가"를 보는 용도다.

정확도 수치는 공개 실제 계좌(scripts/backtest_berka.py)로 말한다. 이 데이터는 우리가 규칙을 알고 만든 것이라 정확도 근거로 쓰지 않는다.

가게 한 곳 = 매출처 3~10곳(매월 결제일), 매입처 2~5곳(매월 또는 매주), 임대료·공과금(±10%)·인건비·대출 상환, 선택적으로 카드 매출(매일, 들쭉날쭉).
조절하는 조건:
- delay: 매출처별 평균 지연일 수준. 거래처마다 0~2배 사이로 흩어지고, 매번 지연은 평균 주변에서 흔들린다
- noise: 0이면 정기 거래만, 1이면 카드 매출·가끔 빠지는 입금(5%)·금액 흔들림(±15%)을 넣는다
- 주말 결제는 다음 월요일로 밀린다
금액 단위는 원. 난수는 seed로 고정한다 (같은 seed면 같은 데이터).
"""
import random
from dataclasses import dataclass, field
from datetime import date, timedelta

from .schedule import clamp_day
from .transactions import Txn


@dataclass
class Store:
    store_id: int
    start_balance: int
    sales: list[tuple[str, int, int, float]] = field(default_factory=list)  # (이름, 결제일, 금액, 평균 지연일)
    terms: list[tuple[str, str, int, int]] = field(default_factory=list)  # 대표자가 등록할 약속 일정 (이름, 주기, 결제일·요일, 금액 ±)
    txns: list[Txn] = field(default_factory=list)


def _business_day(d: date) -> date:
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def _months(start: date, months: int):
    y, m = start.year, start.month
    for _ in range(months):
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def make_store(store_id: int, start: date, months: int, delay: float, noise: float, seed: int) -> Store:
    rnd = random.Random(seed * 10_007 + store_id)
    n_sales = rnd.randint(3, 10)
    revenue = rnd.randint(15, 60) * 1_000_000  # 월 외상 매출 1,500만~6,000만 원
    weights = [rnd.random() + 0.3 for _ in range(n_sales)]
    sales = [(f"매출처{chr(65 + i)}", rnd.choice([5, 7, 10, 15, 20, 25, 28]), round(revenue * w / sum(weights), -4),
              delay * rnd.uniform(0, 2)) for i, w in enumerate(weights)]
    buys = [(f"매입처{chr(65 + i)}", rnd.choice(["MONTHLY", "WEEKLY"]), rnd.choice([1, 3, 10, 12, 25])) for i in range(rnd.randint(2, 5))]
    rent, labor = round(revenue * rnd.uniform(0.05, 0.1), -4), round(revenue * rnd.uniform(0.1, 0.18), -4)
    loan = round(revenue * rnd.uniform(0.02, 0.06), -4)
    card_daily = revenue * 0.25 / 30 if noise else 0  # 카드 매출 (외상 매출의 25% 수준)
    st = Store(store_id=store_id, start_balance=round(revenue * rnd.uniform(0.15, 0.4), -4), sales=sales)
    # 한 달 순이익을 들어오는 돈의 1~3%로 맞춘다: 잔액이 한쪽으로만 흘러가지 않고 달마다 오르내리게
    inflow = revenue + card_daily * 30 * 1.13  # lognormal(0, 0.5) 평균 ≈ 1.13
    fixed = rent + labor + loan + revenue * 0.02
    buy_amt = (inflow * (1 - rnd.uniform(0.01, 0.03)) - fixed) / len(buys)
    st.terms = ([(n, "MONTHLY", d, a) for n, d, a, _ in sales]
                + [(n, c, d if c == "MONTHLY" else (d % 7) + 1, -round(buy_amt if c == "MONTHLY" else buy_amt / 4.3, -3)) for n, c, d in buys]
                + [("임대료", "MONTHLY", 10, -rent), ("인건비", "MONTHLY", 25, -labor), ("운영자금대출 상환", "MONTHLY", 15, -loan),
                   ("공과금", "MONTHLY", 20, -round(revenue * 0.02, -3))])
    ev: list[tuple[date, int, str]] = []
    wobble = lambda: 1 + rnd.uniform(-0.15, 0.15) * noise  # noqa: E731
    for y, m in _months(start, months):
        for name, day, amt, mu in sales:
            if noise and rnd.random() < 0.05:
                continue  # 가끔 그달 입금이 빠진다
            late = max(0, round(rnd.gauss(mu, max(1.0, mu * 0.4)))) if mu else 0
            ev.append((_business_day(clamp_day(y, m, day) + timedelta(days=late)), round(amt * wobble(), -3), name))
        for name, cycle, day in buys:
            amt = buy_amt
            if cycle == "MONTHLY":
                ev.append((_business_day(clamp_day(y, m, day)), -round(amt * wobble(), -3), name))
            else:
                d = date(y, m, 1)
                while d.month == m:
                    if d.isoweekday() == (day % 7) + 1:
                        ev.append((d, -round(amt / 4.3 * wobble(), -3), name))
                    d += timedelta(days=1)
        ev.append((_business_day(clamp_day(y, m, 10)), -rent, "임대료"))
        ev.append((_business_day(clamp_day(y, m, 25)), -labor, "인건비"))
        ev.append((_business_day(clamp_day(y, m, 15)), -loan, "운영자금대출 상환"))
        ev.append((_business_day(clamp_day(y, m, 20)), -round(revenue * 0.02 * (1 + rnd.uniform(-0.1, 0.1)), -3), "공과금"))
        if card_daily:
            d = date(y, m, 1)
            while d.month == m:
                ev.append((d, round(card_daily * rnd.lognormvariate(0, 0.5), -3), "카드매출 입금"))
                d += timedelta(days=1)
    end = date(*list(_months(start, months + 1))[-1], 1)
    bal = st.start_balance
    for d, amt, name in sorted((e for e in ev if e[0] < end), key=lambda e: (e[0], -e[1])):
        bal += amt
        st.txns.append(Txn(day=d, desc=name, amount=amt, balance=bal))
    return st
