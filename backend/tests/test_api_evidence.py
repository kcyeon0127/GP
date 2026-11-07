"""US-07 API: AC-02 근거 ID와 함께 근거 표시, AC-03 근거 없음. 문서 근거는 임베딩 서버(SSH 터널 8101)가 있을 때만 확인한다."""
import httpx
import pytest
from tests.helpers import register_sample

from app.config import EMBEDDING_API_KEY, EMBEDDING_URL
from app.repositories import embedding_client, graph_repository
from app.services.evidence_service import DOCS_DOWN


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


def test_evidence_paths_when_embedding_down(client, monkeypatch):
    """임베딩 서버가 꺼져 있어도 500 대신 경로 근거(P)와 안내 문구를 돌려준다."""
    def down(_texts):
        raise httpx.ConnectError("embedding down")
    monkeypatch.setattr(embedding_client, "embed", down)
    if not client.get("/api/counterparties").json():  # 앞 테스트가 건너뛰어졌으면 여기서 등록
        register_sample(client)
    client.post("/api/graph/sync")
    run_id = client.post("/api/forecasts", json={"base_date": "2026-11-01", "current_balance": 1_000_000}).json()["run_id"]
    res = client.get(f"/api/alerts/{run_id}/evidence")
    assert res.status_code == 200
    ev = res.json()
    assert ev["evidence"] and all(e["type"] == "GRAPH_PATH" for e in ev["evidence"])
    assert ev["message"] == DOCS_DOWN


def test_evidence_covers_schedule_edited_after_last_sync(client, monkeypatch):
    """결제일을 고치면 예정 입출금 ID가 바뀌므로, 수동 동기화 없이도 고친 거래처의 경로가 근거에 나와야 한다 (시연 대본 3~5장면)."""
    def down(_texts):
        raise httpx.ConnectError("embedding down")
    monkeypatch.setattr(embedding_client, "embed", down)
    if not client.get("/api/counterparties").json():
        register_sample(client)
    client.post("/api/graph/sync")
    hanbit = next(c for c in client.get("/api/counterparties").json() if c["name"] == "한빛식자재")
    body = {k: hanbit[k] for k in ("name", "trade_type", "pay_cycle", "amount")} | {"pay_day": 27}
    client.put(f"/api/counterparties/{hanbit['counterparty_id']}", json=body).raise_for_status()
    run_id = client.post("/api/forecasts", json={"base_date": "2026-11-01", "current_balance": 1_000_000}).json()["run_id"]
    texts = [e["text"] for e in client.get(f"/api/alerts/{run_id}/evidence").json()["evidence"]]
    assert any("11/27 한빛식자재 정산" in t for t in texts)


def test_documents_summary_counts_only_this_business(client):
    assert client.get("/api/documents/summary").json() == {"documents": 0, "chunks": 0}
