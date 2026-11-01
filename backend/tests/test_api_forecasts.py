"""US-03·04 API: AC-01 84일 잔액, AC-04 일정 없음 → 수평선·안내, 최초 부족일·부족액."""
from tests.helpers import register_sample


def test_empty_schedule_flat_line(client):
    r = client.post("/api/forecasts", json={}).json()
    assert r["has_events"] is False and "등록" in r["message"]
    assert len(r["daily"]) == 84 and {d["balance"] for d in r["daily"]} == {1_000_000}


def test_shortage_date_and_amount(client):
    register_sample(client)
    r = client.post("/api/forecasts", json={"base_date": "2026-11-01", "current_balance": 1_000_000}).json()
    # 1,000,000 + 1,200,000(11/5) - 1,500,000(11/10) - 2,800,000(11/25) = -2,100,000
    assert (r["first_shortage_date"], r["shortage_amount"]) == ("2026-11-25", 2_100_000)
    assert r["daily"][0]["date"] == "2026-11-01"
    assert client.get(f"/api/forecasts/{r['run_id']}/daily").json()[24] == {"date": "2026-11-25", "balance": -2_100_000}


def test_no_shortage_message(client):
    r = client.post("/api/forecasts", json={"current_balance": 50_000_000}).json()
    assert r["first_shortage_date"] is None and r["message"] == "부족 예상 없음"
