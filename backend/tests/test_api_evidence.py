"""US-07 API: AC-02 근거 ID와 함께 근거 표시, AC-03 근거 없음. 문서 근거는 임베딩 서버(SSH 터널 8101)가 있을 때만 확인한다."""
import httpx
import pytest
from tests.helpers import register_sample

from app.config import EMBEDDING_API_KEY, EMBEDDING_URL
from app.repositories import graph_repository


@pytest.fixture(scope="module", autouse=True)
def cleanup_graph(client):
    yield
    graph_repository.query("MATCH (n {business_id: 999}) DETACH DELETE n")


def embedding_up() -> bool:
    try:
        return httpx.get(f"{EMBEDDING_URL}/models", headers={"Authorization": f"Bearer {EMBEDDING_API_KEY}"}, timeout=3).status_code == 200
    except httpx.HTTPError:
        return False


def test_evidence_paths(client):
    if not embedding_up():
        pytest.skip("임베딩 서버(SSH 터널 8101)가 없어 건너뛴다")
    register_sample(client)
    client.post("/api/graph/sync")
    run_id = client.post("/api/forecasts", json={"base_date": "2026-11-01", "current_balance": 1_000_000}).json()["run_id"]
    ev = client.get(f"/api/alerts/{run_id}/evidence").json()
    ids = [e["id"] for e in ev["evidence"]]
    assert ids and ids[0] == "P1" and ev["message"] is None
    assert any(e["text"].startswith("사업장 → 운영자금대출 → ○○은행 대출 약정 → 11/25") for e in ev["evidence"])
    assert len({e["ref"] for e in ev["evidence"]}) == len(ev["evidence"])  # 같은 근거가 두 번 나오지 않는다


def test_evidence_none_when_green(client):
    r = client.post("/api/forecasts", json={"current_balance": 50_000_000}).json()
    assert r["signal"] == "GREEN"
    assert client.get(f"/api/alerts/{r['run_id']}/evidence").json() == {"run_id": r["run_id"], "evidence": [], "message": "근거 없음"}
