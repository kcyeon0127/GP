"""US-02: 고정비·대출 상환 일정 CRUD (T6). 저장하면 월·분기 지급 일정이 만들어진다 (T7)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_session
from ..domain.enums import CashSource, ContractType, CounterpartyRole, PayCycle
from ..models import Business, Contract, Counterparty, FixedCost, Loan
from ..schemas import FixedCostIn, FixedCostOut, LoanIn, LoanOut
from ..services import schedule_service
from .common import due_dates_of
from .deps import business

router = APIRouter(prefix="/api")


# ---------- 고정비 ----------
def _fc_out(s: Session, f: FixedCost) -> FixedCostOut:
    payee = s.get(Contract, f.contract_id).counterparty.name if f.contract_id else None
    return FixedCostOut(fixed_cost_id=f.fixed_cost_id, name=f.name, pay_cycle=f.pay_cycle.value, pay_day=f.pay_day, months=f.months,
                        amount=f.amount, payee=payee, next_due_dates=due_dates_of(s, CashSource.FIXED_COST, f.fixed_cost_id))


def _payee_contract(s: Session, b: Business, payee: str | None, ctype: ContractType, role: CounterpartyRole, cycle: PayCycle, day: int, amount: int) -> int | None:
    """고정비·대출의 상대(임대인·금융기관)를 거래처와 계약으로 만들어 금융지도에 연결한다 (BASED_ON)."""
    if not payee:
        return None
    cp = s.scalar(select(Counterparty).where(Counterparty.business_id == b.business_id, Counterparty.name == payee))
    if cp is None:
        cp = Counterparty(business_id=b.business_id, name=payee, role=role)
        s.add(cp)
        s.flush()
    c = Contract(business_id=b.business_id, counterparty_id=cp.counterparty_id, contract_type=ctype, pay_cycle=cycle, pay_day=day, amount=amount)
    s.add(c)
    s.flush()
    return c.contract_id


@router.get("/fixed-costs", response_model=list[FixedCostOut])
def list_fixed_costs(s: Session = Depends(get_session), b: Business = Depends(business)):
    return [_fc_out(s, f) for f in s.scalars(select(FixedCost).where(FixedCost.business_id == b.business_id).order_by(FixedCost.fixed_cost_id))]


@router.post("/fixed-costs", response_model=FixedCostOut, status_code=201)
def create_fixed_cost(body: FixedCostIn, s: Session = Depends(get_session), b: Business = Depends(business)):
    cycle = PayCycle(body.pay_cycle)
    cid = _payee_contract(s, b, body.payee, ContractType.LEASE, CounterpartyRole.SUPPLIER, cycle, body.pay_day, body.amount)
    f = FixedCost(business_id=b.business_id, name=body.name, pay_cycle=cycle, pay_day=body.pay_day, months=body.months, amount=body.amount, contract_id=cid)
    s.add(f)
    s.flush()
    schedule_service.for_fixed_cost(s, b, f)
    s.commit()
    return _fc_out(s, f)


@router.put("/fixed-costs/{fixed_cost_id}", response_model=FixedCostOut)
def update_fixed_cost(fixed_cost_id: int, body: FixedCostIn, s: Session = Depends(get_session), b: Business = Depends(business)):
    f = s.get(FixedCost, fixed_cost_id)
    if not f or f.business_id != b.business_id:
        raise HTTPException(404, detail="고정비가 없습니다")
    f.name, f.pay_cycle, f.pay_day, f.months, f.amount = body.name, PayCycle(body.pay_cycle), body.pay_day, body.months, body.amount
    s.flush()
    schedule_service.for_fixed_cost(s, b, f)
    s.commit()
    return _fc_out(s, f)


@router.delete("/fixed-costs/{fixed_cost_id}", status_code=204)
def delete_fixed_cost(fixed_cost_id: int, s: Session = Depends(get_session), b: Business = Depends(business)):
    f = s.get(FixedCost, fixed_cost_id)
    if not f or f.business_id != b.business_id:
        raise HTTPException(404, detail="고정비가 없습니다")
    schedule_service.remove(s, b, CashSource.FIXED_COST, f.fixed_cost_id)
    s.delete(f)
    s.commit()


# ---------- 대출 ----------
def _loan_out(s: Session, l: Loan) -> LoanOut:
    return LoanOut(loan_id=l.loan_id, name=l.name, lender=l.lender, principal=l.principal, interest_rate=float(l.interest_rate), rate_type=l.rate_type,
                   installment=l.installment, repay_day=l.repay_day, maturity_date=l.maturity_date, next_due_dates=due_dates_of(s, CashSource.LOAN, l.loan_id))


@router.get("/loans", response_model=list[LoanOut])
def list_loans(s: Session = Depends(get_session), b: Business = Depends(business)):
    return [_loan_out(s, l) for l in s.scalars(select(Loan).where(Loan.business_id == b.business_id).order_by(Loan.loan_id))]


@router.post("/loans", response_model=LoanOut, status_code=201)
def create_loan(body: LoanIn, s: Session = Depends(get_session), b: Business = Depends(business)):
    cid = _payee_contract(s, b, body.lender, ContractType.LOAN, CounterpartyRole.LENDER, PayCycle.MONTHLY, body.repay_day, body.installment)
    l = Loan(business_id=b.business_id, contract_id=cid, **body.model_dump())
    s.add(l)
    s.flush()
    schedule_service.for_loan(s, b, l)
    s.commit()
    return _loan_out(s, l)


@router.put("/loans/{loan_id}", response_model=LoanOut)
def update_loan(loan_id: int, body: LoanIn, s: Session = Depends(get_session), b: Business = Depends(business)):
    l = s.get(Loan, loan_id)
    if not l or l.business_id != b.business_id:
        raise HTTPException(404, detail="대출이 없습니다")
    for k, v in body.model_dump().items():
        setattr(l, k, v)
    s.flush()
    schedule_service.for_loan(s, b, l)
    s.commit()
    return _loan_out(s, l)


@router.delete("/loans/{loan_id}", status_code=204)
def delete_loan(loan_id: int, s: Session = Depends(get_session), b: Business = Depends(business)):
    l = s.get(Loan, loan_id)
    if not l or l.business_id != b.business_id:
        raise HTTPException(404, detail="대출이 없습니다")
    schedule_service.remove(s, b, CashSource.LOAN, l.loan_id)
    s.delete(l)
    s.commit()
