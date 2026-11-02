"""US-05 API: AC-01 빨간 신호, AC-04 영향 일정 (경보일 전 지출·경보일 뒤 입금)."""
from tests.helpers import register_sample


def test_red_signal_and_drivers(client):
    register_sample(client)
    r = client.post("/api/forecasts", json={"base_date": "2026-11-01", "current_balance": 1_000_000}).json()
    cur = client.get("/api/alerts/current").json()
    assert cur["run_id"] == r["run_id"] and cur["signal"] == "RED"
    d = client.get(f"/api/alerts/{r['run_id']}/drivers").json()
    roles = {(x["date"], x["label"], x["role"]) for x in d["drivers"]}
    assert ("2026-11-25", "운영자금대출 상환", "BEFORE") in roles and ("2026-11-28", "한빛식자재 정산", "AFTER") in roles


def test_green_has_no_drivers(client):
    r = client.post("/api/forecasts", json={"current_balance": 50_000_000}).json()
    assert r["signal"] == "GREEN"
    assert client.get(f"/api/alerts/{r['run_id']}/drivers").json()["drivers"] == []
