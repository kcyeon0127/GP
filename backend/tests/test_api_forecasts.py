"""US-03 API: AC-01 84일 잔액, AC-04 일정 없음 → 수평선·안내."""


def test_empty_schedule_flat_line(client):
    r = client.post("/api/forecasts", json={}).json()
    assert r["has_events"] is False and "등록" in r["message"]
    assert len(r["daily"]) == 84 and {d["balance"] for d in r["daily"]} == {1_000_000}
