"""입력 편의: 거래내역 CSV에서 정기 일정 후보 찾기. 후보만 돌려주고 저장은 기존 등록 API가 한다.

US-17: 읽지 못한 행(형식·결측·중복)을 줄 번호·사유로 돌려주고 정상 행만 쓴다. 표기만 다른 거래처 이름은 병합을 제안한다.
"""
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
    # US-17: 사장님이 승인한 이름 병합 {파일에 적힌 표기: 남길 이름}. 승인한 뒤 같은 파일을 다시 보내면 묶어서 찾는다.
    merges: dict[str, str] = Field(default_factory=dict, max_length=500)


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
        txns, issues = tx.parse_checked(body.text)
    except tx.CsvFormatError as e:
        raise HTTPException(422, detail=str(e))
    registered = _registered(s, b)
    last = tx.last_balance(txns)
    merges = {k: v.strip() for k, v in body.merges.items() if v.strip()}
    found = [(c, tx.same_schedule(c, registered)) for c in tx.detect(txns, merges)]
    names = [r.name for r in registered if r.name]
    # 이미 승인한 병합은 다시 제안하지 않는다
    suggest = [m for m in tx.merge_suggestions(txns, names) if not all(merges.get(n, n) == m.to for n in m.names)]
    return {
        "rows": len(txns),
        "issues": [dict(line=x.line, reason=x.reason, text=x.text) for x in issues],
        "merge_suggestions": [dict(to=m.to, names=m.names, count=m.count) for m in suggest],
        "period": [txns[0].day, txns[-1].day],
        "last_balance": {"date": last[0], "balance": last[1]} if last else None,
        "candidates": [dict(name=c.name, direction=c.direction, kind=c.kind, pay_cycle=c.pay_cycle, pay_day=c.pay_day, amount=c.amount,
                            months=c.months, count=c.count, dates=c.dates, varies=c.varies, already=same is not None, same_as=same)
                       for c, same in found],
    }
