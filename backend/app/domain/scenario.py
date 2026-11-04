"""What-if 시나리오 규칙 (US-09). 원본 일정을 복사해 조건을 적용한 새 목록을 돌려주는 순수 함수다.

- 정산 지연: 고른 매출처의 입금 날짜를 days일 뒤로 민다. 12주 밖으로 밀린 입금은 계산 구간에서 빠진다.
- 매출 감소: 모든 매출 입금을 pct% 줄인다.
- 원가 상승: 매입 대금(매입처 지급)을 pct% 늘린다. 고정비·대출 상환은 그대로 둔다.
- 금리 상승: 변동금리 대출의 월 상환액에 대출 잔액 × pp%p ÷ 12 를 더한다 (이자만 늘어난다고 본다).
금액은 원 단위로 반올림한다. 원본 목록은 바꾸지 않는다 (AC-06).
"""
from dataclasses import dataclass, replace
from datetime import date, timedelta


@dataclass(frozen=True)
class Item:
    event_id: int
    due_date: date
    amount: int  # 입금 +, 출금 -
    label: str
    kind: str  # SALES / PURCHASE / FIXED_COST / LOAN
    party_id: int | None = None  # 매출·매입처 counterparty_id
    variable_principal: int | None = None  # 변동금리 대출이면 대출 잔액


@dataclass(frozen=True)
class Conditions:
    delay_counterparty_id: int | None = None
    delay_days: int = 0
    revenue_drop_pct: float = 0
    cost_rise_pct: float = 0
    rate_rise_pp: float = 0

    def kinds(self) -> list[str]:
        out = []
        if self.delay_counterparty_id and self.delay_days:
            out.append("SETTLEMENT_DELAY")
        if self.revenue_drop_pct:
            out.append("REVENUE_DROP")
        if self.cost_rise_pct:
            out.append("COST_RISE")
        if self.rate_rise_pp:
            out.append("RATE_RISE")
        return out


def apply(items: list[Item], c: Conditions) -> list[Item]:
    out: list[Item] = []
    for it in items:
        new = it
        if it.kind == "SALES":
            if c.delay_counterparty_id and it.party_id == c.delay_counterparty_id and c.delay_days:
                new = replace(new, due_date=new.due_date + timedelta(days=c.delay_days))
            if c.revenue_drop_pct:
                new = replace(new, amount=round(new.amount * (1 - c.revenue_drop_pct / 100)))
        # 고정비는 올리지 않는다: 임대료·인건비는 원가 상승과 바로 연동되지 않고, AC-05도 매입 지급만 본다.
        elif it.kind == "PURCHASE" and c.cost_rise_pct:
            new = replace(new, amount=round(new.amount * (1 + c.cost_rise_pct / 100)))
        # 잔액 × %p ÷ 12로 단순화한다: 만기는 선택 입력이라 원리금을 다시 계산할 수 없고, 12주 안에서는 잔액 변화가 작다.
        elif it.kind == "LOAN" and it.variable_principal and c.rate_rise_pp:
            new = replace(new, amount=new.amount - round(it.variable_principal * c.rate_rise_pp / 100 / 12))
        out.append(new)
    return out
