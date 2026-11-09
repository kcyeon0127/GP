"""API 테스트 공용 데이터."""


def register_sample(c) -> None:
    """정산 지연 사례: 11/5 +120만, 11/10 임대료 -150만, 11/25 원리금 -280만, 11/28 정산 +300만."""
    c.post("/api/counterparties", json={"name": "청춘마켓", "trade_type": "SALES", "pay_cycle": "MONTHLY", "pay_day": 5, "amount": 1_200_000}).raise_for_status()
    c.post("/api/fixed-costs", json={"name": "임대료", "pay_cycle": "MONTHLY", "pay_day": 10, "amount": 1_500_000, "payee": "건물주"}).raise_for_status()
    c.post("/api/loans", json={"name": "운영자금대출", "lender": "○○은행", "principal": 60_000_000, "interest_rate": 5.1,
                               "rate_type": "VARIABLE", "installment": 2_800_000, "repay_day": 25}).raise_for_status()
    c.post("/api/counterparties", json={"name": "한빛식자재", "trade_type": "SALES", "pay_cycle": "MONTHLY", "pay_day": 28, "amount": 3_000_000}).raise_for_status()


def add_contract_doc(party: str, key: str, title: str) -> str:
    """거래 상대(party)의 계약에 문서 조각 하나를 붙인다. 임베딩 서버 없이 쓰려고 0 벡터를 넣는다. 조각 키를 돌려준다."""
    from sqlalchemy import select

    from app.config import EMBEDDING_DIM
    from app.db import SessionLocal
    from app.models import Contract, Counterparty, Document, DocumentChunk

    with SessionLocal() as s:
        c = s.scalars(select(Contract).join(Counterparty).where(Counterparty.name == party)).first()
        doc = Document(business_id=c.business_id, contract_id=c.contract_id, key=key, title=title)
        s.add(doc)
        s.flush()
        s.add(DocumentChunk(document_id=doc.document_id, contract_id=c.contract_id, key=f"{key}-1", text=f"{title} 지급 조건", embedding=[0.0] * EMBEDDING_DIM))
        s.commit()
    return f"{key}-1"


def doc_evidence(*chunk_keys: str):
    """근거 검색 대역: 주어진 문서 조각만 D 근거로 돌려준다 (Neo4j·임베딩 서버 없이)."""
    def collect(s, r):
        ev = [{"id": f"D{i}", "type": "DOCUMENT_CHUNK", "ref": k, "text": f"{k} 조항", "score": 0.8} for i, k in enumerate(chunk_keys, 1)]
        return {"run_id": r.run_id, "evidence": ev, "message": None if ev else "근거 없음"}
    return collect
