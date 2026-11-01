"""US-01: 거래처·결제 조건 CRUD (T2). 저장하면 ScheduleService가 12주 예정일을 만든다 (T3)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_session
from ..domain.enums import CashSource, ContractType, CounterpartyRole
from ..models import Business, Contract, Counterparty
from ..schemas import CounterpartyIn, CounterpartyOut
from ..services import schedule_service
from .common import due_dates_of
from .deps import business

router = APIRouter(prefix="/api")


def _dup(s: Session, b: Business, name: str, exclude: int | None = None) -> None:
    q = select(Counterparty.counterparty_id).where(Counterparty.business_id == b.business_id, Counterparty.name == name)
    found = s.scalar(q)
    if found and found != exclude:
        raise HTTPException(409, detail="이미 등록된 거래처 이름입니다")


def _cp_out(s: Session, cp: Counterparty) -> CounterpartyOut:
    c = cp.contracts[0]
    return CounterpartyOut(counterparty_id=cp.counterparty_id, contract_id=c.contract_id, name=cp.name, trade_type=c.contract_type.value,
                           pay_cycle=c.pay_cycle, pay_day=c.pay_day, amount=c.amount, start_date=c.start_date, end_date=c.end_date,
                           next_due_dates=due_dates_of(s, CashSource.CONTRACT, c.contract_id))


def _trade_contracts(s: Session, b: Business):
    return s.scalars(select(Counterparty).join(Contract).where(Counterparty.business_id == b.business_id,
                     Contract.contract_type.in_([ContractType.SALES, ContractType.PURCHASE])).order_by(Counterparty.counterparty_id)).unique()


@router.get("/counterparties", response_model=list[CounterpartyOut])
def list_counterparties(s: Session = Depends(get_session), b: Business = Depends(business)):
    return [_cp_out(s, cp) for cp in _trade_contracts(s, b)]


@router.post("/counterparties", response_model=CounterpartyOut, status_code=201)
def create_counterparty(body: CounterpartyIn, s: Session = Depends(get_session), b: Business = Depends(business)):
    _dup(s, b, body.name)
    cp = Counterparty(business_id=b.business_id, name=body.name, role=CounterpartyRole.CUSTOMER if body.trade_type == "SALES" else CounterpartyRole.SUPPLIER)
    c = Contract(business_id=b.business_id, contract_type=ContractType(body.trade_type), pay_cycle=body.pay_cycle, pay_day=body.pay_day,
                 amount=body.amount, start_date=body.start_date, end_date=body.end_date)
    cp.contracts.append(c)
    s.add(cp)
    s.flush()
    schedule_service.for_contract(s, b, c)
    s.commit()
    return _cp_out(s, cp)


@router.put("/counterparties/{counterparty_id}", response_model=CounterpartyOut)
def update_counterparty(counterparty_id: int, body: CounterpartyIn, s: Session = Depends(get_session), b: Business = Depends(business)):
    cp = s.get(Counterparty, counterparty_id)
    if not cp or cp.business_id != b.business_id:
        raise HTTPException(404, detail="거래처가 없습니다")
    _dup(s, b, body.name, exclude=counterparty_id)
    cp.name = body.name
    cp.role = CounterpartyRole.CUSTOMER if body.trade_type == "SALES" else CounterpartyRole.SUPPLIER
    c = cp.contracts[0]
    c.contract_type, c.pay_cycle, c.pay_day, c.amount = ContractType(body.trade_type), body.pay_cycle, body.pay_day, body.amount
    c.start_date, c.end_date = body.start_date, body.end_date
    s.flush()
    schedule_service.for_contract(s, b, c)
    s.commit()
    return _cp_out(s, cp)


@router.delete("/counterparties/{counterparty_id}", status_code=204)
def delete_counterparty(counterparty_id: int, s: Session = Depends(get_session), b: Business = Depends(business)):
    cp = s.get(Counterparty, counterparty_id)
    if not cp or cp.business_id != b.business_id:
        raise HTTPException(404, detail="거래처가 없습니다")
    for c in cp.contracts:  # 연결된 계약의 예정 입출금도 함께 지운다
        schedule_service.remove(s, b, CashSource.CONTRACT, c.contract_id)
    s.delete(cp)
    s.commit()
