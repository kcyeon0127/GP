"""US-08 위험 영향 경로: 경로 규칙 (domain) 과 경로 API. API 테스트는 Neo4j가 필요하다."""
from datetime import date, timedelta

import pytest
from tests.helpers import register_sample

from app.domain import cashflow_engine
from app.domain import impact_path as ip
from app.domain import scenario as sc

BASE = date(2026, 11, 1)


def _case(cond: sc.Conditions, start=1_000_000):
    """거래처 C(party 3) 11/5 +500만, 11/6 매입 -300만, 11/6 임대료 -200만, 11/8 대출 -100만, 11/20 매출 +600만."""
    items = [
        sc.Item(event_id=1, due_date=date(2026, 11, 5), amount=5_000_000, label="거래처C 정산", kind="SALES", party_id=3),
        sc.Item(event_id=2, due_date=date(2026, 11, 6), amount=-2_000_000, label="임대료", kind="FIXED_COST"),
        sc.Item(event_id=3, due_date=date(2026, 11, 6), amount=-3_000_000, label="대성유통 매입 대금", kind="PURCHASE", party_id=9),
        sc.Item(event_id=4, due_date=date(2026, 11, 8), amount=-1_000_000, label="운영자금대출 상환", kind="LOAN", variable_principal=60_000_000),
        sc.Item(event_id=5, due_date=date(2026, 11, 20), amount=6_000_000, label="청춘마켓 정산", kind="SALES", party_id=4),
    ]
    after = sc.apply(items, cond)
    f = lambda xs: cashflow_engine.forecast(BASE, start, 0, [(i.due_date, i.amount) for i in xs]).daily  # noqa: E731
    sources = {1: ip.Source("CONTRACT", 31), 2: ip.Source("FIXED_COST", 41), 3: ip.Source("CONTRACT", 32), 4: ip.Source("LOAN", 51), 5: ip.Source("CONTRACT", 33)}
    return ip.build(BASE, items, after, f(items), f(after), sources, cond.kinds())


def test_delay_path_order_ac01_ac02():
    out = _case(sc.Conditions(delay_counterparty_id=3, delay_days=15))
    roles = [s["role"] for s in out["steps"]]
    assert roles == ["CAUSE", "SHORTAGE", "PAYMENT", "PAYMENT", "PAYMENT"]
    cause = out["steps"][0]
    assert cause["source"] == ip.Source("CONTRACT", 31) and cause["after_date"] == date(2026, 11, 20) and cause["amount"] == -5_000_000
    assert out["shortage"]["first_date"] == date(2026, 11, 6) and out["shortage"]["last_date"] == date(2026, 11, 19)
    pays = [s for s in out["steps"] if s["role"] == "PAYMENT"]
    # 11/6 두 건은 금액 큰 매입 대금이 먼저, 그다음 임대료, 11/8 대출 상환
    assert [(p["order"], p["label"]) for p in pays] == [(1, "대성유통 매입 대금"), (2, "임대료"), (3, "운영자금대출 상환")]
    assert all(p["new"] for p in pays)  # 기준안에서는 모두 낼 수 있었다


def test_evidence_ids_follow_path_ac04():
    out = _case(sc.Conditions(delay_counterparty_id=3, delay_days=15))
    assert [s["evidence_id"] for s in out["steps"]] == ["P1", None, "P2", "P3", "P4"]
    assert all(s["date"] and s["amount"] for s in out["steps"])


def test_no_risk_empty_path_ac03():
    out = _case(sc.Conditions(revenue_drop_pct=1), start=20_000_000)
    assert out["steps"] == [] and out["shortage"] is None


def test_shortage_after_four_weeks_is_empty():
    later = [(BASE + timedelta(days=i), 1 if i < 28 else -1) for i in range(84)]
    assert ip.shortage_window(BASE, later) is None


def test_cost_rise_causes_are_purchases():
    out = _case(sc.Conditions(cost_rise_pct=100))
    causes = [s for s in out["steps"] if s["role"] == "CAUSE"]
    assert [c["source"] for c in causes] == [ip.Source("CONTRACT", 32)] and causes[0]["amount"] == -3_000_000


# ---------- API (Neo4j 필요) ----------

@pytest.fixture(scope="module", autouse=True)
def cleanup_graph():
    yield
    try:
        from app.repositories import graph_repository
        graph_repository.query("MATCH (n {business_id: 999}) DETACH DELETE n")
    except Exception:
        pass


def _cp_id(client, name):
    return next(c["counterparty_id"] for c in client.get("/api/counterparties").json() if c["name"] == name)


def test_api_impact_path_ac01_ac06(client):
    register_sample(client)
    client.post("/api/forecasts", json={})
    delay = client.post("/api/scenarios", json={"settlement_delay": {"counterparty_id": _cp_id(client, "청춘마켓"), "days": 10}}).json()
    p = client.get(f"/api/scenarios/{delay['scenario_id']}/impact-path").json()
    assert [s["role"] for s in p["steps"]][:2] == ["CAUSE", "SHORTAGE"]
    cause = p["steps"][0]
    assert cause["label"].startswith("청춘마켓") and [n["label"] for n in cause["nodes"]] == ["Counterparty", "Contract"]
    pay = next(s for s in p["steps"] if s["role"] == "PAYMENT")
    assert pay["order"] == 1 and pay["label"] == "임대료" and pay["date"] == "2026-11-10" and pay["evidence_id"]
    assert {"label": "FixedCost", "id": pay["source"]["id"]} in pay["nodes"]
    # AC-06: 다른 시나리오를 고르면 그 시나리오 기준 경로
    rate = client.post("/api/scenarios", json={"rate_rise_pp": 1}).json()
    q = client.get(f"/api/scenarios/{rate['scenario_id']}/impact-path").json()
    assert q["kinds"] == ["RATE_RISE"] and q["steps"] != p["steps"]
    ids = [x["scenario_id"] for x in client.get("/api/scenarios").json()]
    assert ids[:2] == [rate["scenario_id"], delay["scenario_id"]]


def test_api_impact_path_404(client):
    assert client.get("/api/scenarios/987654321/impact-path").status_code == 404
