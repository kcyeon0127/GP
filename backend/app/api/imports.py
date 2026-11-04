"""입력 편의: 거래내역 CSV에서 정기 일정 후보 찾기. 후보만 돌려주고 저장은 기존 등록 API가 한다."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_session
from ..domain import transactions as tx
from ..domain.enums import ContractType
from ..models import Business, Contract, Counterparty, FixedCost, Loan
from .deps import business

router = APIRouter(prefix="/api")


# 파일 업로드(multipart)가 아니라 텍스트로 받는다: python-multipart 의존성을 늘리지 않고,
# 은행 파일의 EUC-KR은 브라우저 TextDecoder로 풀 수 있기 때문이다.
class ImportIn(BaseModel):
    text: str = Field(min_length=1, max_length=5_000_000, description="CSV 파일 내용 (화면에서 UTF-8/EUC-KR을 풀어 보낸다)")


def _registered(s: Session, b: Business) -> list[tx.Registered]:
    bid = b.business_id
    out = []
    for c in s.scalars(select(Contract).where(Contract.business_id == bid, Contract.contract_type.in_([ContractType.SALES, ContractType.PURCHASE]))):
        direction = "IN" if c.contract_type == ContractType.SALES else "OUT"
        out.append(tx.Registered(c.counterparty.name, direction, c.pay_cycle.value, c.pay_day, c.amount))
    for f in s.scalars(select(FixedCost).where(FixedCost.business_id == bid)):
        out.append(tx.Registered(f.name, "OUT", f.pay_cycle.value, f.pay_day, f.amount))
    for ln in s.scalars(select(Loan).where(Loan.business_id == bid)):
        out.append(tx.Registered(ln.name, "OUT", "MONTHLY", ln.repay_day, ln.installment))
    # 받는 곳·금융기관은 일정이 아니라 거래 상대라 비교 대상이 아니지만, 같은 이름으로 거래처를 만들면 409로 막힌다
    used = {n for n in s.scalars(select(Counterparty.name).where(Counterparty.business_id == bid))} - {r.name for r in out}
    return out + [tx.Registered(n, "", "", 0, 0) for n in sorted(used)]


@router.post("/imports/transactions")
def import_transactions(body: ImportIn, s: Session = Depends(get_session), b: Business = Depends(business)):
    try:
        txns = tx.parse_csv(body.text)
    except tx.CsvFormatError as e:
        raise HTTPException(422, detail=str(e))
    registered = _registered(s, b)
    last = tx.last_balance(txns)
    found = [(c, tx.same_schedule(c, registered)) for c in tx.detect(txns)]
    return {
        "rows": len(txns),
        "period": [txns[0].day, txns[-1].day],
        "last_balance": {"date": last[0], "balance": last[1]} if last else None,
        "candidates": [dict(name=c.name, direction=c.direction, kind=c.kind, pay_cycle=c.pay_cycle, pay_day=c.pay_day, amount=c.amount,
                            months=c.months, count=c.count, dates=c.dates, varies=c.varies, already=same is not None, same_as=same)
                       for c, same in found],
    }
