"""US-06 API: AC-01 그래프 구축, AC-02 라벨별 노드 수 = PostgreSQL 건수 (재실행해도 같음). Neo4j가 필요하다."""
import pytest
from tests.helpers import register_sample

from app.repositories import graph_repository


@pytest.fixture(scope="module", autouse=True)
def cleanup_graph(client):
    yield
    graph_repository.query("MATCH (n {business_id: 999}) DETACH DELETE n")


def test_graph_sync_counts_match(client):
    register_sample(client)
    first = client.post("/api/graph/sync").json()
    again = client.post("/api/graph/sync").json()
    assert first["consistent"] and again["consistent"] and first["neo4j"] == again["neo4j"]
    assert first["neo4j"]["Counterparty"] == 4 and first["relationships"]["GENERATES"] == first["neo4j"]["CashEvent"]
    g = client.get("/api/graph").json()
    assert {"Business", "Counterparty", "Contract", "FixedCost", "Loan"} <= {n["label"] for n in g["nodes"]} and g["edges"]
