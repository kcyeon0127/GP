"""US-01 API: AC-01 저장·예정일, AC-02 결제 주기 누락, AC-04 중복 이름. PostgreSQL gp_test가 필요하다."""


def test_counterparty_create_and_due_dates(client):
    """AC-01: 저장 → 목록 표시, 12주 예정일 생성."""
    r = client.post("/api/counterparties", json={"name": "청춘마켓", "trade_type": "SALES", "pay_cycle": "MONTHLY", "pay_day": 5, "amount": 1_200_000})
    assert r.status_code == 201
    assert r.json()["next_due_dates"] == ["2026-11-05", "2026-12-05", "2027-01-05"]
    assert [c["name"] for c in client.get("/api/counterparties").json()] == ["청춘마켓"]


def test_counterparty_missing_cycle_422(client):
    """AC-02: 결제 주기 미입력 → 저장 거부, 빠진 칸 안내."""
    r = client.post("/api/counterparties", json={"name": "A상회", "trade_type": "SALES", "pay_day": 5, "amount": 100})
    assert r.status_code == 422 and r.json()["fields"] == ["pay_cycle"]


def test_counterparty_duplicate_409(client):
    """AC-04: 같은 이름 → 저장 거부, 중복 안내."""
    r = client.post("/api/counterparties", json={"name": "청춘마켓", "trade_type": "SALES", "pay_cycle": "MONTHLY", "pay_day": 1, "amount": 100})
    assert r.status_code == 409 and "이미" in r.json()["detail"]


def test_counterparty_update_and_delete(client):
    cid = client.get("/api/counterparties").json()[0]["counterparty_id"]
    r = client.put(f"/api/counterparties/{cid}", json={"name": "청춘마켓", "trade_type": "SALES", "pay_cycle": "MONTHLY", "pay_day": 31, "amount": 1_000_000})
    assert r.json()["next_due_dates"] == ["2026-11-30", "2026-12-31"]  # 31일 → 11/30 말일 보정
    assert client.delete(f"/api/counterparties/{cid}").status_code == 204
    assert client.get("/api/counterparties").json() == []
