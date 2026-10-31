"""GraphRepository: Neo4j 접근만 한다 (판단 없음)."""
from neo4j import Driver, GraphDatabase

from ..config import NEO4J_PASSWORD, NEO4J_URI, NEO4J_USER

LABEL_KEYS = {
    "Business": "business_id",
    "Counterparty": "counterparty_id",
    "Contract": "contract_id",
    "FixedCost": "fixed_cost_id",
    "Loan": "loan_id",
    "CashEvent": "cash_event_id",
    "DocumentChunk": "chunk_id",
}

_driver: Driver | None = None


def driver() -> Driver:
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    return _driver


def query(cypher: str, **params) -> list[dict]:
    records, _, _ = driver().execute_query(cypher, params, database_="neo4j")
    return [r.data() for r in records]


def ensure_constraints() -> None:
    """T19: 라벨마다 id 속성 UNIQUE 제약."""
    for label, key in LABEL_KEYS.items():
        query(f"CREATE CONSTRAINT {label.lower()}_id IF NOT EXISTS FOR (n:{label}) REQUIRE n.{key} IS UNIQUE")


def constraint_names() -> list[str]:
    return [r["name"] for r in query("SHOW CONSTRAINTS YIELD name RETURN name")]
