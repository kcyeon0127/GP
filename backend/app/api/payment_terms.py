"""US-14: 거래 패턴 기반 결제조건 자동 추정 (T2)과 확정 저장·재계산 (T4).

추정은 저장하지 않는다. 대표자가 화면에서 확인·수정해 확정한 값만 저장하고, 확정하면 예상 잔액을 다시 계산한다.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_session
from ..domain import payment_terms as pt
from ..domain import transactions as tx
from ..domain.enums import ContractType, PayCycle
from ..models import Business, ConfirmedTerm, Contract, Counterparty
from ..services import forecast_service, schedule_service
from .deps import business
from .imports import ImportIn

router = APIRouter(prefix="/api")


def _sales(s: Session, b: Business) -> list[tuple[Counterparty, Contract]]:
    rows = s.execute(select(Counterparty, Contract).join(Contract).where(Counterparty.business_id == b.business_id, Contract.contract_type == ContractType.SALES))
    return [(cp, c) for cp, c in rows]


@router.post("/payment-terms/estimate")
def estimate_terms(body: ImportIn, s: Session = Depends(get_session), b: Business = Depends(business)):
    """거래내역 CSV(US-17과 같은 입력)로 매출처별 결제 주기·결제일·평균 지연일을 추정한다."""
    try:
        txns, issues = tx.parse_checked(body.text)
    except tx.CsvFormatError as e:
        raise HTTPException(422, detail=str(e))
    sales = _sales(s, b)
    registered = [pt.Registered(cp.counterparty_id, cp.name, c.pay_cycle.value, c.pay_day) for cp, c in sales]
    confirmed = {t.counterparty_id: t for t in s.scalars(select(ConfirmedTerm).where(ConfirmedTerm.business_id == b.business_id))}
    merges = {k: v.strip() for k, v in body.merges.items() if v.strip()}
    out = []
    for e in pt.estimate(txns, registered, merges):
        ct = confirmed.get(e.counterparty_id)
        out.append(dict(name=e.name, status=e.status, count=e.count, dates=e.dates, amount=e.amount, counterparty_id=e.counterparty_id,
                        registered={"pay_cycle": e.registered_cycle, "pay_day": e.registered_day} if e.counterparty_id else None,
                        pay_cycle=e.pay_cycle, pay_day=e.pay_day, avg_delay_days=e.avg_delay_days, max_delay_days=e.max_delay_days,
                        delays=e.delays, basis=e.basis, confirmed_delay_days=ct.delay_days if ct else None))
    return {"period": [txns[0].day, txns[-1].day], "skipped_rows": len(issues), "estimates": out}


class ConfirmIn(BaseModel):
    pay_cycle: PayCycle | None = Field(default=None, description="바꾸면 등록 결제조건도 고친다")
    pay_day: int | None = Field(default=None, ge=1, le=31)
    delay_days: int = Field(ge=0, le=60, description="확정한 평균 지연일")
    sample_count: int = Field(ge=0, description="추정에 쓴 입금 건수")


@router.get("/payment-terms")
def confirmed_terms(s: Session = Depends(get_session), b: Business = Depends(business)):
    rows = s.scalars(select(ConfirmedTerm).where(ConfirmedTerm.business_id == b.business_id))
    return [dict(counterparty_id=t.counterparty_id, delay_days=t.delay_days, sample_count=t.sample_count, confirmed_at=t.confirmed_at) for t in rows]


@router.put("/payment-terms/{counterparty_id}")
def confirm_term(counterparty_id: int, body: ConfirmIn, s: Session = Depends(get_session), b: Business = Depends(business)):
    cp = s.get(Counterparty, counterparty_id)
    c = next((x for x in cp.contracts if x.contract_type == ContractType.SALES), None) if cp and cp.business_id == b.business_id else None
    if c is None:
        raise HTTPException(404, detail="매출처가 없습니다")
    cycle = body.pay_cycle or c.pay_cycle
    day = body.pay_day or c.pay_day
    if cycle == PayCycle.WEEKLY and day > 7:
        raise HTTPException(422, detail="주간 결제는 요일 번호(1~7)를 입력하세요")
    if (cycle, day) != (c.pay_cycle, c.pay_day):
        c.pay_cycle, c.pay_day = cycle, day
        s.flush()
        schedule_service.for_contract(s, b, c)
    t = s.get(ConfirmedTerm, counterparty_id) or ConfirmedTerm(counterparty_id=counterparty_id, business_id=b.business_id)
    t.delay_days, t.sample_count, t.confirmed_at = body.delay_days, body.sample_count, datetime.now()
    s.add(t)
    s.flush()
    r = forecast_service.run(s, b)  # T4: 확정하면 예상 잔액·최초 부족일을 다시 계산한다
    s.commit()
    return {"counterparty_id": counterparty_id, "pay_cycle": c.pay_cycle.value, "pay_day": c.pay_day, "delay_days": t.delay_days,
            "forecast": {"run_id": r.run_id, "signal": r.signal.value, "first_shortage_date": r.first_shortage_date, "shortage_amount": r.shortage_amount}}
