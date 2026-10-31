"""API 통합 테스트 (PostgreSQL gp_test, Neo4j 사업장 999번). docker compose up -d 가 필요하다.

US-01 AC-01·02·04, US-02 AC-01·03, US-03 AC-01·04, US-04 AC-01, US-05 AC-01·04, US-06 AC-01·02, US-07 AC-02·03.
"""
from datetime import date

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import EMBEDDING_API_KEY, EMBEDDING_URL
from app.db import Base, engine
from app.main import app


@pytest.fixture(scope="module")
def client():
    from app import models  # noqa: F401

    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
    Base.metadata.drop_all(engine)
    with TestClient(app) as c:
        c.post("/api/forecasts", json={"base_date": "2026-11-01", "current_balance": 1_000_000, "safety_balance": 1_000_000})
        yield c


def embedding_up() -> bool:
    try:
        return httpx.get(f"{EMBEDDING_URL}/models", headers={"Authorization": f"Bearer {EMBEDDING_API_KEY}"}, timeout=3).status_code == 200
    except httpx.HTTPError:
        return False


def test_empty_schedule_flat_line(client):
    """US-03 AC-04: 일정이 없으면 수평선과 등록 안내."""
    r = client.post("/api/forecasts", json={}).json()
    assert r["has_events"] is False and "등록" in r["message"]
    assert len(r["daily"]) == 84 and {d["balance"] for d in r["daily"]} == {1_000_000}


def test_counterparty_create_and_due_dates(client):
    """US-01 AC-01: 저장 → 목록 표시, 12주 예정일 생성."""
    r = client.post("/api/counterparties", json={"name": "청춘마켓", "trade_type": "SALES", "pay_cycle": "MONTHLY", "pay_day": 5, "amount": 1_200_000})
    assert r.status_code == 201
    assert r.json()["next_due_dates"] == ["2026-11-05", "2026-12-05", "2027-01-05"]
    assert [c["name"] for c in client.get("/api/counterparties").json()] == ["청춘마켓"]


def test_counterparty_missing_cycle_422(client):
    """US-01 AC-02: 결제 주기 미입력 → 저장 거부, 빠진 칸 안내."""
    r = client.post("/api/counterparties", json={"name": "A상회", "trade_type": "SALES", "pay_day": 5, "amount": 100})
    assert r.status_code == 422 and r.json()["fields"] == ["pay_cycle"]


def test_counterparty_duplicate_409(client):
    """US-01 AC-04: 같은 이름 → 저장 거부, 중복 안내."""
    r = client.post("/api/counterparties", json={"name": "청춘마켓", "trade_type": "SALES", "pay_cycle": "MONTHLY", "pay_day": 1, "amount": 100})
    assert r.status_code == 409 and "이미" in r.json()["detail"]


def test_fixed_cost_and_loan(client):
    """US-02 AC-01·02: 월 25일 임대료·원리금 → 12주 일정. AC-03: 금액 0·지급일 누락 → 빠진 칸."""
    r = client.post("/api/fixed-costs", json={"name": "임대료", "pay_cycle": "MONTHLY", "pay_day": 10, "amount": 1_500_000, "payee": "건물주"})
    assert r.status_code == 201 and r.json()["next_due_dates"] == ["2026-11-10", "2026-12-10", "2027-01-10"]
    r = client.post("/api/loans", json={"name": "운영자금대출", "lender": "○○은행", "principal": 60_000_000, "interest_rate": 5.1,
                                         "rate_type": "VARIABLE", "installment": 2_800_000, "repay_day": 25})
    assert r.status_code == 201 and r.json()["next_due_dates"] == ["2026-11-25", "2026-12-25"]
    bad = client.post("/api/fixed-costs", json={"name": "공과금", "pay_cycle": "MONTHLY", "amount": 0})
    assert bad.status_code == 422 and bad.json()["fields"] == ["amount", "pay_day"]


def test_forecast_red_shortage_and_drivers(client):
    """US-03 AC-01, US-04 AC-01 형태, US-05 AC-01·04: 정산 지연 상황에서 빨강·부족일·영향 일정."""
    client.post("/api/counterparties", json={"name": "한빛식자재", "trade_type": "SALES", "pay_cycle": "MONTHLY", "pay_day": 28, "amount": 3_000_000})
    r = client.post("/api/forecasts", json={"base_date": "2026-11-01", "current_balance": 1_000_000}).json()
    # 1,000,000 + 1,200,000(11/5) - 1,500,000(11/10) - 2,800,000(11/25) = -2,100,000
    assert (r["signal"], r["first_shortage_date"], r["shortage_amount"]) == ("RED", "2026-11-25", 2_100_000)
    assert len(r["daily"]) == 84 and r["daily"][0]["date"] == "2026-11-01"
    assert client.get(f"/api/forecasts/{r['run_id']}/daily").json()[24] == {"date": "2026-11-25", "balance": -2_100_000}
    cur = client.get("/api/alerts/current").json()
    assert cur["run_id"] == r["run_id"] and cur["signal"] == "RED"
    d = client.get(f"/api/alerts/{r['run_id']}/drivers").json()
    roles = {(x["date"], x["label"], x["role"]) for x in d["drivers"]}
    assert ("2026-11-25", "운영자금대출 상환", "BEFORE") in roles and ("2026-11-28", "한빛식자재 정산", "AFTER") in roles


def test_graph_sync_counts_match(client):
    """US-06 AC-01·02: 그래프 구축 → 라벨별 노드 수가 PostgreSQL 건수와 일치, 재실행해도 같다."""
    first = client.post("/api/graph/sync").json()
    again = client.post("/api/graph/sync").json()
    assert first["consistent"] and again["consistent"] and first["neo4j"] == again["neo4j"]
    assert first["neo4j"]["Counterparty"] == 4 and first["relationships"]["GENERATES"] == first["neo4j"]["CashEvent"]
    g = client.get("/api/graph").json()
    labels = {n["label"] for n in g["nodes"]}
    assert {"Business", "Counterparty", "Contract", "FixedCost", "Loan"} <= labels and g["edges"]


def test_evidence_paths(client):
    """US-07 AC-02: 경보의 근거가 근거 ID와 함께 나온다 (그래프 경로)."""
    if not embedding_up():
        pytest.skip("임베딩 서버(SSH 터널 8101)가 없어 문서 근거는 건너뛴다")
    run_id = client.get("/api/alerts/current").json()["run_id"]
    ev = client.get(f"/api/alerts/{run_id}/evidence").json()
    ids = [e["id"] for e in ev["evidence"]]
    assert ids and ids[0] == "P1" and ev["message"] is None
    assert any("운영자금대출" in e["text"] and "○○은행" in e["text"] for e in ev["evidence"])


def test_evidence_none_when_green(client):
    """US-07 AC-03: 경보가 없으면 빈 결과와 "근거 없음"."""
    r = client.post("/api/forecasts", json={"current_balance": 50_000_000}).json()
    assert r["signal"] == "GREEN"
    ev = client.get(f"/api/alerts/{r['run_id']}/evidence").json()
    assert ev == {"run_id": r["run_id"], "evidence": [], "message": "근거 없음"}
