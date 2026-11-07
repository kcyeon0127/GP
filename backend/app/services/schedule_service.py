"""ScheduleService: 결제 조건·고정비·대출 상환에서 12주 예정 입출금(CashEvent)을 만든다 (T3·T7)."""
import json
from datetime import date

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..domain.enums import CashDirection, CashSource, ContractType, PlanStatus
from ..domain.schedule import due_dates, parse_months
from ..models import Business, CashEvent, Contract, FixedCost, Loan, ResponsePlan

# 매입·매출 계약만 스스로 입출금을 만든다. 임대(LEASE)·대출(LOAN) 계약은 고정비·대출 행이 만든다.
EVENT_CONTRACT_TYPES = {ContractType.SALES: CashDirection.IN, ContractType.PURCHASE: CashDirection.OUT}


def approved_plans(s: Session, business_id: int, source: CashSource | None = None, source_id: int | None = None) -> list[ResponsePlan]:
    q = select(ResponsePlan).where(ResponsePlan.business_id == business_id, ResponsePlan.status == PlanStatus.APPROVED)
    if source is not None:
        q = q.where(ResponsePlan.source_type == source, ResponsePlan.source_id == source_id)
    return list(s.scalars(q))


def apply_plans(rows: list[CashEvent], plans: list[ResponsePlan]) -> list[CashEvent]:
    """승인한 대응안을 다시 만든 예정 입출금에 적용한다 (US-10 AC-03).

    원래 날짜·금액이 같은 행만 바꾼다. 대표가 그 뒤 결제 조건을 고쳐 금액이나 날짜가 달라졌다면
    승인 당시의 안이 더는 맞지 않으므로 적용하지 않는다.
    """
    out = list(rows)
    for p in plans:
        hit = next((r for r in out if r.due_date == p.original_date and r.amount == p.original_amount), None)
        if hit is None:
            continue
        out.remove(hit)
        out += [CashEvent(business_id=hit.business_id, source_type=hit.source_type, source_id=hit.source_id, label=hit.label,
                          direction=hit.direction, amount=x["amount"], due_date=date.fromisoformat(x["due_date"]))
                for x in json.loads(p.parts)]
    return sorted(out, key=lambda r: r.due_date)


def _replace(s: Session, b: Business, source: CashSource, source_id: int, rows: list[CashEvent]) -> list[CashEvent]:
    rows = apply_plans(rows, approved_plans(s, b.business_id, source, source_id)) if rows else rows
    s.execute(delete(CashEvent).where(CashEvent.business_id == b.business_id, CashEvent.source_type == source, CashEvent.source_id == source_id))
    s.add_all(rows)
    s.flush()
    return rows


def for_contract(s: Session, b: Business, c: Contract) -> list[CashEvent]:
    direction = EVENT_CONTRACT_TYPES.get(c.contract_type)
    rows = []
    if direction:
        label = f"{c.counterparty.name} {'정산' if direction == CashDirection.IN else '매입 대금'}"
        rows = [CashEvent(business_id=b.business_id, source_type=CashSource.CONTRACT, source_id=c.contract_id, label=label,
                          direction=direction, amount=c.amount, due_date=d)
                for d in due_dates(c.pay_cycle, c.pay_day, b.base_date, start=c.start_date, end=c.end_date)]
    return _replace(s, b, CashSource.CONTRACT, c.contract_id, rows)


def for_fixed_cost(s: Session, b: Business, f: FixedCost) -> list[CashEvent]:
    rows = [CashEvent(business_id=b.business_id, source_type=CashSource.FIXED_COST, source_id=f.fixed_cost_id, label=f.name,
                      direction=CashDirection.OUT, amount=f.amount, due_date=d)
            for d in due_dates(f.pay_cycle, f.pay_day, b.base_date, months=parse_months(f.months))]
    return _replace(s, b, CashSource.FIXED_COST, f.fixed_cost_id, rows)


def for_loan(s: Session, b: Business, l: Loan) -> list[CashEvent]:
    from ..domain.enums import PayCycle

    rows = [CashEvent(business_id=b.business_id, source_type=CashSource.LOAN, source_id=l.loan_id, label=f"{l.name} 상환",
                      direction=CashDirection.OUT, amount=l.installment, due_date=d)
            for d in due_dates(PayCycle.MONTHLY, l.repay_day, b.base_date, end=l.maturity_date)]
    return _replace(s, b, CashSource.LOAN, l.loan_id, rows)


def remove(s: Session, b: Business, source: CashSource, source_id: int) -> None:
    _replace(s, b, source, source_id, [])


def regenerate_all(s: Session, b: Business) -> None:
    """기준일이 바뀌면 모든 예정 입출금을 다시 만든다."""
    for c in s.scalars(select(Contract).where(Contract.business_id == b.business_id)):
        for_contract(s, b, c)
    for f in s.scalars(select(FixedCost).where(FixedCost.business_id == b.business_id)):
        for_fixed_cost(s, b, f)
    for l in s.scalars(select(Loan).where(Loan.business_id == b.business_id)):
        for_loan(s, b, l)


def regenerate_source(s: Session, b: Business, source: CashSource, source_id: int) -> None:
    """출처 하나의 예정 입출금만 다시 만든다 (대응안 승인·취소 후)."""
    model, make = {CashSource.CONTRACT: (Contract, for_contract), CashSource.FIXED_COST: (FixedCost, for_fixed_cost),
                   CashSource.LOAN: (Loan, for_loan)}[source]
    obj = s.get(model, source_id)
    if obj is not None:
        make(s, b, obj)
