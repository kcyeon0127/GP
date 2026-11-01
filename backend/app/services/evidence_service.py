"""EvidenceService (T25): 경보의 부족 일정에서 거래관계 경로(Neo4j)와 계약 문서 조각(pgvector)을 모아 근거 ID를 만든다.

근거 ID 형식 (run 단위로 고정):
- P{n}: 그래프 경로 (거래처 → 계약 → 예정 입출금, 또는 사업장 → 대출/고정비 → 계약 → 예정 입출금)
- D{n}: 계약 문서 조각
번호는 먼저 막히는 지급 순서(due_date)다. 근거가 없으면 빈 목록과 "근거 없음"을 돌려준다 (US-07 AC-03).
"""
from sqlalchemy import delete
from sqlalchemy.orm import Session

from ..config import EVIDENCE_MIN_SCORE
from ..domain.enums import EvidenceRef
from ..models import Evidence, ForecastRun
from ..repositories import document_repository, embedding_client
from ..repositories import graph_repository as g
from . import forecast_service

PATH_CYPHER = """
MATCH (src)-[:GENERATES]->(e:CashEvent) WHERE e.cash_event_id IN $ids
OPTIONAL MATCH (src)-[:BASED_ON]->(base:Contract)
WITH e, src, CASE WHEN src:Contract THEN src ELSE base END AS k
OPTIONAL MATCH (c:Counterparty)-[:PARTY_TO]->(k)
RETURN e.cash_event_id AS event_id, e.due_date AS due_date, labels(src)[0] AS src_label, src.name AS src_name,
       k.contract_id AS contract_id, k.contract_type AS contract_type, c.name AS counterparty
ORDER BY e.due_date, e.cash_event_id
"""
CONTRACT_KO = {"SALES": "매출 계약", "PURCHASE": "매입 계약", "LEASE": "계약", "LOAN": "대출 약정"}


def collect(s: Session, r: ForecastRun) -> dict:
    drv = forecast_service.drivers(s, r)
    if not drv:
        return {"run_id": r.run_id, "evidence": [], "message": "근거 없음"}
    by_id = {e.cash_event_id: (e, role) for e, role in drv}
    items: list[dict] = []
    contract_events: dict[int, list] = {}
    for p in g.query(PATH_CYPHER, ids=list(by_id)):
        e, role = by_id[p["event_id"]]
        contract = f"{p['counterparty']} {CONTRACT_KO.get(p['contract_type'], '계약')}" if p["contract_id"] else None
        if p["src_label"] == "Contract":
            chain = [contract]
        else:  # 고정비·대출: 사업장 → 고정비/대출 → (근거 계약)
            chain = ["사업장", p["src_name"]] + ([contract] if contract else [])
        when = "경보일 전에 나가는 돈" if role == "BEFORE" else "경보일 뒤에 들어오는 돈"
        items.append(dict(ref_type=EvidenceRef.GRAPH_PATH, ref_id=f"event:{e.cash_event_id}",
                          text=f"{' → '.join(chain)} → {e.due_date:%m/%d} {e.label} {e.amount:,}원 ({when})"))
        if p["contract_id"]:
            contract_events.setdefault(p["contract_id"], []).append(e)
    # 경로에 나온 계약마다 그 계약서에서 가장 관련 있는 조항 1개 (유사도가 기준 이상일 때만)
    for cid, evs in contract_events.items():
        query = f"{evs[0].label} 지급 지연 연체 시 조항"
        vec = embedding_client.embed([query])[0]
        for chunk, doc, score in document_repository.search(s, r.business_id, vec, limit=1, contract_ids=[cid]):
            if score >= EVIDENCE_MIN_SCORE:
                items.append(dict(ref_type=EvidenceRef.DOCUMENT_CHUNK, ref_id=chunk.key, text=f"{doc.title} {chunk.text}", score=round(score, 3)))

    s.execute(delete(Evidence).where(Evidence.run_id == r.run_id))
    out, n_p, n_d = [], 0, 0
    for rank, it in enumerate(items, 1):
        if it["ref_type"] == EvidenceRef.GRAPH_PATH:
            n_p += 1
            eid = f"P{n_p}"
        else:
            n_d += 1
            eid = f"D{n_d}"
        s.add(Evidence(evidence_id=f"R{r.run_id}-{eid}", run_id=r.run_id, ref_type=it["ref_type"], ref_id=it["ref_id"], rank=rank, text=it["text"]))
        out.append({"id": eid, "type": it["ref_type"].value, "ref": it["ref_id"], "text": it["text"], **({"score": it["score"]} if "score" in it else {})})
    s.flush()
    return {"run_id": r.run_id, "evidence": out, "message": None if out else "근거 없음"}


def search_question(s: Session, business_id: int, question: str, k: int = 3) -> list[str]:
    """T27 평가용: 질문 하나에 대해 근거 조각 키(예: D06-3)를 유사도 순으로 돌려준다.

    질문에 거래처·대출 이름이 있으면 그 계약의 조각을 먼저 본다(그래프로 범위 좁히기).
    """
    vec = embedding_client.embed([question])[0]
    names = g.query("""MATCH (c:Counterparty {business_id: $bid})-[:PARTY_TO]->(k:Contract) RETURN c.name AS name, k.contract_id AS cid
                       UNION MATCH (l:Loan {business_id: $bid})-[:BASED_ON]->(k:Contract) RETURN l.name AS name, k.contract_id AS cid""", bid=business_id)
    scoped = sorted({n["cid"] for n in names if n["name"] and n["name"].split()[0] in question})
    hits = document_repository.search(s, business_id, vec, limit=k, contract_ids=scoped) if scoped else []
    rest = document_repository.search(s, business_id, vec, limit=k)
    seen, out = set(), []
    for c, _, score in hits + rest:
        if c.key not in seen and score >= EVIDENCE_MIN_SCORE:
            seen.add(c.key)
            out.append(c.key)
    return out[:k]
