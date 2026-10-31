"""시연용 사업장(한결 식자재 납품) 데이터를 API로 등록하고, 계약 문서를 임베딩해 넣고(T24), 그래프를 동기화한다.

실행 (backend 폴더): .venv/bin/python -m scripts.seed_demo
필요: docker compose up -d, 임베딩 서버 SSH 터널 (ssh -N -L 8101:127.0.0.1:8101 lab)
기존 사업장 데이터는 지우고 다시 만든다.
"""
import json
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.db import SessionLocal, init_db
from app.main import app
from app.models import Business, Contract, Counterparty, Document, DocumentChunk, FixedCost, Loan
from app.repositories import embedding_client
from app.repositories.business import get_or_create

DATA = Path(__file__).resolve().parent.parent / "data"

COUNTERPARTIES = [
    dict(name="한빛식자재", trade_type="SALES", pay_cycle="MONTHLY", pay_day=7, amount=3_200_000),
    dict(name="청춘마켓", trade_type="SALES", pay_cycle="MONTHLY", pay_day=13, amount=2_100_000),
    dict(name="온누리푸드", trade_type="SALES", pay_cycle="MONTHLY", pay_day=21, amount=4_000_000),
    dict(name="대성유통", trade_type="PURCHASE", pay_cycle="MONTHLY", pay_day=9, amount=1_800_000),
]
FIXED_COSTS = [
    dict(name="임대료", pay_cycle="MONTHLY", pay_day=6, amount=1_500_000, payee="건물주"),
    dict(name="인건비", pay_cycle="MONTHLY", pay_day=11, amount=3_200_000, payee="직원"),
    dict(name="공과금", pay_cycle="MONTHLY", pay_day=15, amount=400_000),
    dict(name="화재보험료", pay_cycle="QUARTERLY", pay_day=31, amount=300_000, payee="○○화재"),
]
LOANS = [
    dict(name="운영자금대출", lender="○○은행", principal=62_000_000, interest_rate=5.1, rate_type="VARIABLE", installment=2_400_000, repay_day=15),
    dict(name="시설자금대출", lender="△△은행", principal=18_000_000, interest_rate=3.8, rate_type="FIXED", installment=900_000, repay_day=25),
]
# 계약 문서 → 연결할 거래처(계약 상대) 이름. A카드 약관은 등록된 계약이 없어 연결하지 않는다.
DOC_PARTY = {"D01": "한빛식자재", "D02": "청춘마켓", "D03": "온누리푸드", "D04": "대성유통", "D05": "건물주",
             "D06": "○○은행", "D07": "△△은행", "D08": "직원", "D09": None, "D10": "○○화재"}


def reset(s, bid):
    for model in (Document, FixedCost, Loan, Counterparty):
        s.execute(delete(model).where(model.business_id == bid))
    s.commit()


def main():
    init_db()
    with SessionLocal() as s:
        b = get_or_create(s)
        b.name = "한결 식자재 납품"
        s.commit()
        reset(s, b.business_id)
    c = TestClient(app)
    c.post("/api/forecasts", json={"base_date": "2026-11-01", "current_balance": 3_200_000, "safety_balance": 1_000_000})
    for body in COUNTERPARTIES:
        c.post("/api/counterparties", json=body).raise_for_status()
    for body in FIXED_COSTS:
        c.post("/api/fixed-costs", json=body).raise_for_status()
    for body in LOANS:
        c.post("/api/loans", json=body).raise_for_status()

    docs = json.loads((DATA / "contracts.json").read_text())
    with SessionLocal() as s:
        b = get_or_create(s)
        texts, rows = [], []
        for d in docs:
            party = DOC_PARTY[d["doc"]]
            cid = s.scalar(select(Contract.contract_id).join(Counterparty).where(Counterparty.business_id == b.business_id, Counterparty.name == party)) if party else None
            doc = Document(business_id=b.business_id, contract_id=cid, key=d["doc"], title=d["title"])
            s.add(doc)
            s.flush()
            for i, text in enumerate(d["chunks"], 1):
                rows.append(DocumentChunk(document_id=doc.document_id, contract_id=cid, key=f"{d['doc']}-{i}", text=text, embedding=None))
                texts.append(f"{d['title']} {text}")
        for row, vec in zip(rows, embedding_client.embed(texts)):
            row.embedding = vec
        s.add_all(rows)
        s.commit()
        print(f"문서 {len(docs)}건, 조각 {len(rows)}개 임베딩 적재")
    print("그래프:", json.dumps(c.post("/api/graph/sync").json(), ensure_ascii=False))
    r = c.post("/api/forecasts", json={}).json()
    print("예상 잔액:", r["signal"], r["message"])


if __name__ == "__main__":
    main()
