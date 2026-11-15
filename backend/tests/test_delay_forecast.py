"""US-15 입금 지연 반영 예측: 보수 예측(T5), 두 곡선 응답(T6), 지연 이력 없으면 기본과 같음(T7)."""
from datetime import date

from tests.helpers import register_sample

from app.domain import payment_terms as pt
from app.domain import scenario as sc


def _items():
    return [sc.Item(1, date(2026, 11, 5), 1_000_000, "청춘마켓 정산", "SALES", party_id=1),
            sc.Item(2, date(2026, 11, 7), 2_000_000, "한빛식자재 정산", "SALES", party_id=2),
            sc.Item(3, date(2026, 11, 8), -500_000, "대성유통 매입 대금", "PURCHASE", party_id=3)]


def test_apply_delays_moves_only_confirmed_sales():
    after = pt.apply_delays(_items(), {2: 5, 3: 9})
    assert [i.due_date.day for i in after] == [5, 12, 8]  # 매입처 지연값은 무시, 입금만 민다


def test_no_delay_is_same_as_base_t7():
    items = _items()
    assert pt.apply_delays(items, {}) == items and pt.apply_delays(items, {1: 0}) == items


def _cp_id(client, name):
    return next(c["counterparty_id"] for c in client.get("/api/counterparties").json() if c["name"] == name)


def test_api_conservative_curve(client):
    register_sample(client)
    base = client.post("/api/forecasts", json={}).json()
    assert base["conservative"]["applied"] == 0
    assert base["conservative"]["first_shortage_date"] == base["first_shortage_date"]  # T7
    assert [d["balance"] for d in base["conservative"]["daily"]] == [d["balance"] for d in base["daily"]]
    cid = _cp_id(client, "청춘마켓")
    client.put(f"/api/payment-terms/{cid}", json={"delay_days": 10, "sample_count": 3}).raise_for_status()
    f = client.post("/api/forecasts", json={}).json()
    c = f["conservative"]
    assert c["applied"] == 1 and any(m.startswith("청춘마켓") for m in c["moved"])
    # 매달 5일 정산이 15일로 밀리면 11/10 임대료 날 잔액이 모자란다 (US-09 정산 지연과 같은 결과)
    assert c["first_shortage_date"] == "2026-11-10" and f["first_shortage_date"] == "2026-11-25"
    assert f["signal"] == base["signal"]  # 홈 경보는 기본 예측 그대로
