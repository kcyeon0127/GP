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
MATCH (e:CashEvent) WHERE e.cash_event_id IN $ids
OPTIONAL MATCH p1 = (:Counterparty)-[:PARTY_TO]->(:Contract)-[:GENERATES]->(e)
OPTIONAL MATCH p2 = (:Counterparty)-[:PARTY_TO]->(:Contract)<-[:BASED_ON]-(src)-[:GENERATES]->(e)
OPTIONAL MATCH p3 = (:Business)-[:PAYS|BORROWS]->(src2)-[:GENERATES]->(e)
WITH e, coalesce(p1, p2, p3) AS p
WHERE p IS NOT NULL
RETURN e.cash_event_id AS event_id, e.due_date AS due_date,
       [n IN nodes(p) | {label: labels(n)[0], name: coalesce(n.name, n.label, n.contract_type), contract_id: n.contract_id}] AS nodes
ORDER BY e.due_date
"""


def collect(s: Session, r: ForecastRun) -> dict:
    drv = forecast_service.drivers(s, r)
    if not drv:
        return {"run_id": r.run_id, "evidence": [], "message": "근거 없음"}
    by_id = {e.cash_event_id: (e, role) for e, role in drv}
    paths = g.query(PATH_CYPHER, ids=list(by_id))
    items: list[dict] = []
    contract_ids: list[int] = []
    for p in sorted(paths, key=lambda x: (x["due_date"], x["event_id"])):
        e, role = by_id[p["event_id"]]
        names = [n["name"] for n in p["nodes"] if n["name"]]
        cids = [n["contract_id"] for n in p["nodes"] if n["label"] == "Contract" and n["contract_id"]]
        contract_ids += [c for c in cids if c not in contract_ids]
        when = "경보일 전에 나가는 돈" if role == "BEFORE" else "경보일 뒤에 들어오는 돈"
        items.append(dict(ref_type=EvidenceRef.GRAPH_PATH, ref_id=f"event:{e.cash_event_id}", contract_ids=cids,
                          text=f"{' → '.join(names)} · {e.due_date:%m/%d} {e.label} {e.amount:,}원 ({when})"))
    if contract_ids:
        query = " ".join(sorted({e.label for e, _ in drv})) + " 지급 지연 연체 결제 조건"
        vec = embedding_client.embed([query])[0]
        for chunk, doc, score in document_repository.search(s, r.business_id, vec, limit=2 * len(contract_ids), contract_ids=contract_ids):
            if score >= EVIDENCE_MIN_SCORE:
                items.append(dict(ref_type=EvidenceRef.DOCUMENT_CHUNK, ref_id=chunk.key, contract_ids=[chunk.contract_id],
                                  text=f"{doc.title} {chunk.text}", score=round(score, 3)))

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
