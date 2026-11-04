"""US-09 What-if 시나리오: 적용 규칙 (domain) 과 시나리오 API."""
from datetime import date, timedelta

from tests.helpers import register_sample

from app.domain import scenario as sc


def _items():
    sales = [sc.Item(event_id=i, due_date=date(2026, 11, 5) + timedelta(days=7 * i), amount=10_000_000, label=f"정산{i}", kind="SALES", party_id=1 + i % 2) for i in range(4)]
    buys = [sc.Item(event_id=10 + i, due_date=date(2026, 11, 10) + timedelta(days=7 * i), amount=-5_000_000, label=f"매입{i}", kind="PURCHASE", party_id=9) for i in range(4)]
    rent = sc.Item(event_id=20, due_date=date(2026, 11, 25), amount=-1_500_000, label="임대료", kind="FIXED_COST")
    loan = sc.Item(event_id=21, due_date=date(2026, 11, 25), amount=-2_800_000, label="대출 상환", kind="LOAN", variable_principal=60_000_000)
    fixed_loan = sc.Item(event_id=22, due_date=date(2026, 11, 25), amount=-900_000, label="시설자금 상환", kind="LOAN")
    return sales + buys + [rent, loan, fixed_loan]


def total(items, kind):
    return sum(i.amount for i in items if i.kind == kind)


def test_revenue_drop_ac04():
    after = sc.apply(_items(), sc.Conditions(revenue_drop_pct=15))
    assert total(_items(), "SALES") == 40_000_000 and total(after, "SALES") == 34_000_000


def test_cost_rise_ac05_only_purchases():
    after = sc.apply(_items(), sc.Conditions(cost_rise_pct=10))
    assert total(after, "PURCHASE") == -22_000_000
    assert total(after, "FIXED_COST") == -1_500_000 and total(after, "LOAN") == -3_700_000  # 고정비·대출은 그대로


def test_rate_rise_variable_loan_only():
    after = {i.event_id: i.amount for i in sc.apply(_items(), sc.Conditions(rate_rise_pp=1))}
    assert after[21] == -2_850_000  # 6,000만 원 × 1%p ÷ 12 = 5만 원 증가
    assert after[22] == -900_000  # 고정금리는 그대로


def test_settlement_delay_moves_one_party():
    after = {i.event_id: i.due_date for i in sc.apply(_items(), sc.Conditions(delay_counterparty_id=1, delay_days=15))}
    assert after[0] == date(2026, 11, 20) and after[1] == date(2026, 11, 12)  # party 1만 밀린다


def test_original_unchanged_ac06():
    items = _items()
    before = list(items)
    sc.apply(items, sc.Conditions(revenue_drop_pct=50, cost_rise_pct=50, rate_rise_pp=5, delay_counterparty_id=1, delay_days=30))
    assert items == before


def _cp_id(client, name):
    return next(c["counterparty_id"] for c in client.get("/api/counterparties").json() if c["name"] == name)


def test_api_delay_new_shortage_ac02(client):
    register_sample(client)
    base = client.post("/api/forecasts", json={}).json()
    assert base["first_shortage_date"] == "2026-11-25"
    r = client.post("/api/scenarios", json={"settlement_delay": {"counterparty_id": _cp_id(client, "청춘마켓"), "days": 10}})
    assert r.status_code == 201
    out = r.json()
    assert out["kinds"] == ["SETTLEMENT_DELAY"]
    assert out["base"]["first_shortage_date"] == "2026-11-25" and out["scenario"]["first_shortage_date"] == "2026-11-10"
    # 매달 5일 정산이 15일로 밀리면 매달 10일 임대료를 그날 낼 수 없게 된다
    assert [(x["date"], x["label"], x["balance"]) for x in out["new_shortages"]] == [
        ("2026-11-10", "임대료", -500_000), ("2026-12-10", "임대료", -600_000), ("2027-01-10", "임대료", -700_000)]
    assert any(ch["label"].startswith("청춘마켓") and ch["after_date"] == "2026-11-15" for ch in out["changes"])
    assert len(out["scenario"]["daily"]) == 84
    # AC-06: 원본 일정과 기준안(홈 경보)은 그대로
    assert client.get("/api/alerts/current").json()["run_id"] == base["run_id"]
    assert client.get(f"/api/scenarios/{out['scenario_id']}/comparison").json()["scenario"]["first_shortage_date"] == "2026-11-10"


def test_api_four_scenarios_ac03(client):
    cid = _cp_id(client, "한빛식자재")
    for body in ({"settlement_delay": {"counterparty_id": cid, "days": 7}}, {"revenue_drop_pct": 15}, {"cost_rise_pct": 10}, {"rate_rise_pp": 1}):
        r = client.post("/api/scenarios", json=body)
        assert r.status_code == 201 and len(r.json()["scenario"]["daily"]) == 84


def test_api_range_ac07(client):
    cid = _cp_id(client, "청춘마켓")
    r = client.post("/api/scenarios", json={"settlement_delay": {"counterparty_id": cid, "days": 0}})
    assert r.status_code == 422 and "days" in r.json()["fields"]
    empty = client.post("/api/scenarios", json={})
    assert empty.status_code == 422 and empty.json()["detail"] == "조건을 하나 이상 고르세요"
    assert client.post("/api/scenarios", json={"revenue_drop_pct": 0}).status_code == 422
