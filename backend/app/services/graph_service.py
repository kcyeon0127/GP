"""GraphService (T20·T21): PostgreSQL 원본을 Neo4j 금융지도로 MERGE하고 조회한다 (양식 6 §3.2)."""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Business, CashEvent, Contract, Counterparty, Document, DocumentChunk, FixedCost, Loan
from ..repositories import graph_repository as g


def _rows(s: Session, model, business_id: int, *cols):
    return [dict(zip([c.key for c in cols], r)) for r in s.execute(select(*cols).where(model.business_id == business_id))]


def sync(s: Session, b: Business) -> dict:
    g.ensure_constraints()
    bid = b.business_id
    # 이전 동기화 뒤 PostgreSQL에서 지운 행은 그래프에서도 지운다. 이 사업장의 노드만 대상이다.
    g.query("MATCH (n {business_id: $bid}) WHERE NOT n:Business DETACH DELETE n", bid=bid)
    g.query("MERGE (b:Business {business_id: $bid}) SET b.name = $name, b.safety_balance = $safe", bid=bid, name=b.name, safe=b.safety_balance)

    cps = _rows(s, Counterparty, bid, Counterparty.counterparty_id, Counterparty.name, Counterparty.role)
    g.query("""UNWIND $rows AS r MERGE (c:Counterparty {counterparty_id: r.counterparty_id})
               SET c.name = r.name, c.role = r.role, c.business_id = $bid
               WITH c MATCH (b:Business {business_id: $bid}) MERGE (b)-[:TRADES_WITH]->(c)""",
            rows=[{**r, "role": r["role"].value} for r in cps], bid=bid)

    cts = _rows(s, Contract, bid, Contract.contract_id, Contract.counterparty_id, Contract.contract_type, Contract.pay_cycle, Contract.pay_day, Contract.amount)
    g.query("""UNWIND $rows AS r MERGE (k:Contract {contract_id: r.contract_id})
               SET k.contract_type = r.contract_type, k.pay_cycle = r.pay_cycle, k.pay_day = r.pay_day, k.amount = r.amount, k.business_id = $bid
               WITH k, r MATCH (b:Business {business_id: $bid}) MERGE (b)-[:HAS_CONTRACT]->(k)
               WITH k, r MATCH (c:Counterparty {counterparty_id: r.counterparty_id}) MERGE (c)-[:PARTY_TO]->(k)""",
            rows=[{**r, "contract_type": r["contract_type"].value, "pay_cycle": r["pay_cycle"].value} for r in cts], bid=bid)

    fcs = _rows(s, FixedCost, bid, FixedCost.fixed_cost_id, FixedCost.name, FixedCost.pay_cycle, FixedCost.pay_day, FixedCost.amount, FixedCost.contract_id)
    g.query("""UNWIND $rows AS r MERGE (f:FixedCost {fixed_cost_id: r.fixed_cost_id})
               SET f.name = r.name, f.pay_cycle = r.pay_cycle, f.pay_day = r.pay_day, f.amount = r.amount, f.business_id = $bid
               WITH f, r MATCH (b:Business {business_id: $bid}) MERGE (b)-[:PAYS]->(f)
               WITH f, r MATCH (k:Contract {contract_id: r.contract_id}) MERGE (f)-[:BASED_ON]->(k)""",
            rows=[{**r, "pay_cycle": r["pay_cycle"].value} for r in fcs], bid=bid)

    lns = _rows(s, Loan, bid, Loan.loan_id, Loan.name, Loan.installment, Loan.repay_day, Loan.rate_type, Loan.maturity_date, Loan.contract_id)
    g.query("""UNWIND $rows AS r MERGE (l:Loan {loan_id: r.loan_id})
               SET l.name = r.name, l.installment = r.installment, l.repay_day = r.repay_day, l.rate_type = r.rate_type,
                   l.maturity_date = r.maturity_date, l.business_id = $bid
               WITH l, r MATCH (b:Business {business_id: $bid}) MERGE (b)-[:BORROWS]->(l)
               WITH l, r MATCH (k:Contract {contract_id: r.contract_id}) MERGE (l)-[:BASED_ON]->(k)""",
            rows=[{**r, "rate_type": r["rate_type"].value, "maturity_date": r["maturity_date"].isoformat() if r["maturity_date"] else None} for r in lns], bid=bid)

    evs = _rows(s, CashEvent, bid, CashEvent.cash_event_id, CashEvent.source_type, CashEvent.source_id, CashEvent.label, CashEvent.direction, CashEvent.amount, CashEvent.due_date)
    label_of = {"CONTRACT": ("Contract", "contract_id"), "FIXED_COST": ("FixedCost", "fixed_cost_id"), "LOAN": ("Loan", "loan_id")}
    for src, (label, key) in label_of.items():
        rows = [{**r, "direction": r["direction"].value, "due_date": r["due_date"].isoformat()} for r in evs if r["source_type"].value == src]
        g.query(f"""UNWIND $rows AS r MERGE (e:CashEvent {{cash_event_id: r.cash_event_id}})
                    SET e.label = r.label, e.direction = r.direction, e.amount = r.amount, e.due_date = r.due_date, e.business_id = $bid
                    WITH e, r MATCH (src:{label} {{{key}: r.source_id}}) MERGE (src)-[:GENERATES]->(e)""", rows=rows, bid=bid)

    chunks = [dict(chunk_id=c, key=k, contract_id=ct) for c, k, ct in s.execute(
        select(DocumentChunk.chunk_id, DocumentChunk.key, DocumentChunk.contract_id).join(Document).where(Document.business_id == bid))]
    g.query("""UNWIND $rows AS r MERGE (d:DocumentChunk {chunk_id: r.chunk_id}) SET d.key = r.key, d.business_id = $bid
               WITH d, r MATCH (k:Contract {contract_id: r.contract_id}) MERGE (d)-[:DESCRIBES]->(k)""", rows=chunks, bid=bid)
    return counts(s, b)


def counts(s: Session, b: Business) -> dict:
    """무결성 규칙 7: 라벨별 Neo4j 노드 수와 PostgreSQL 건수를 비교한다."""
    bid = b.business_id
    pg = {
        "Business": 1,
        "Counterparty": s.scalar(select(func.count()).select_from(Counterparty).where(Counterparty.business_id == bid)),
        "Contract": s.scalar(select(func.count()).select_from(Contract).where(Contract.business_id == bid)),
        "FixedCost": s.scalar(select(func.count()).select_from(FixedCost).where(FixedCost.business_id == bid)),
        "Loan": s.scalar(select(func.count()).select_from(Loan).where(Loan.business_id == bid)),
        "CashEvent": s.scalar(select(func.count()).select_from(CashEvent).where(CashEvent.business_id == bid)),
        "DocumentChunk": s.scalar(select(func.count()).select_from(DocumentChunk).join(Document).where(Document.business_id == bid)),
    }
    neo = {r["label"]: r["n"] for r in g.query(
        "UNWIND $labels AS label CALL { WITH label MATCH (n) WHERE label IN labels(n) AND n.business_id = $bid RETURN count(n) AS n } RETURN label, n",
        labels=list(pg), bid=bid)}
    rels = {r["t"]: r["n"] for r in g.query("MATCH (a {business_id: $bid})-[r]->() RETURN type(r) AS t, count(r) AS n", bid=bid)}
    return {"postgres": pg, "neo4j": neo, "relationships": rels, "consistent": all(pg[k] == neo.get(k, 0) for k in pg)}


def graph_json(b: Business, include_events: bool = False) -> dict:
    """GET /api/graph: 사업장 중심 노드·관계 (Cytoscape.js elements 형식에 맞춘 nodes/edges)."""
    labels = ["Business", "Counterparty", "Contract", "FixedCost", "Loan"] + (["CashEvent"] if include_events else [])
    nodes = g.query("""MATCH (n) WHERE n.business_id = $bid AND any(l IN labels(n) WHERE l IN $labels)
                       RETURN elementId(n) AS id, labels(n)[0] AS label, properties(n) AS props""", bid=b.business_id, labels=labels)
    ids = {n["id"] for n in nodes}
    edges = [e for e in g.query("""MATCH (a)-[r]->(c) WHERE a.business_id = $bid
                                   RETURN elementId(r) AS id, elementId(a) AS source, elementId(c) AS target, type(r) AS type""", bid=b.business_id)
             if e["source"] in ids and e["target"] in ids]
    return {"nodes": nodes, "edges": edges}
