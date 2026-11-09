"""US-10 대응안 비교·승인: 후보 규칙 (domain) 과 대응안 API."""
from datetime import date

import pytest
from tests.helpers import add_contract_doc, doc_evidence, register_sample

from app.domain import response as rp
from app.domain.enums import SignalLevel
from app.services import response_service

ST = rp.Setting(date(2026, 11, 1), 1_000_000, 500_000)


def ev(i, d, amount, kind, label=None, adjusted=False):
    return rp.Event(event_id=i, due_date=date(2026, 11, d), amount=amount, label=label or f"{kind}{i}", kind=kind, adjusted=adjusted)


def test_split_rounds_first_half_down_to_10k():
    assert rp.split(14_200_000) == (7_100_000, 7_100_000)
    assert rp.split(1_234_567) == (610_000, 624_567)


def test_pay_date_shift_picks_least_shift_that_fixes_signal():
    # 11/5 매입 300만으로 부족, 11/8·11/20에 입금. 11/8로 미루면 해결되므로 11/20까지 미루지 않는다.
    events = [ev(1, 5, -3_000_000, "PURCHASE"), ev(2, 8, 4_000_000, "SALES"), ev(3, 20, 4_000_000, "SALES")]
    p = rp.best_plan("PAY_DATE_SHIFT", events, ST)
    assert p and p.parts == [rp.Part(date(2026, 11, 8), 3_000_000)] and p.shift_days == 3
    assert p.forecast.signal == SignalLevel.GREEN


def test_purchase_split_keeps_half_on_original_day():
    events = [ev(1, 5, -1_800_000, "PURCHASE"), ev(2, 8, 4_000_000, "SALES")]
    p = rp.best_plan("PURCHASE_SPLIT", events, ST)
    assert p.parts == [rp.Part(date(2026, 11, 5), 900_000), rp.Part(date(2026, 11, 8), 900_000)]


def test_no_plan_when_nothing_helps():
    # 부족을 만드는 지급 뒤에 들어오는 돈이 없으면 옮길 날이 없다
    assert rp.best_plan("PAY_DATE_SHIFT", [ev(1, 5, -3_000_000, "PURCHASE")], ST) is None


def test_expense_shift_skips_payroll_and_tax():
    events = [ev(1, 5, -3_000_000, "FIXED_COST", "인건비"), ev(2, 6, -100_000, "FIXED_COST", "부가세"), ev(3, 8, 4_000_000, "SALES")]
    assert rp.best_plan("EXPENSE_SHIFT", events, ST) is None


def test_already_adjusted_event_is_not_moved_again():
    events = [ev(1, 5, -3_000_000, "PURCHASE", adjusted=True), ev(2, 8, 4_000_000, "SALES")]
    assert rp.best_plan("PAY_DATE_SHIFT", events, ST) is None


def test_shift_limit_per_kind():
    # 대출은 14일까지만 옮겨 본다
    events = [ev(1, 5, -3_000_000, "LOAN"), ev(2, 25, 4_000_000, "SALES")]
    assert rp.best_plan("LOAN_CHECK", events, ST) is None
    assert rp.best_plan("PAY_DATE_SHIFT", [ev(1, 5, -3_000_000, "PURCHASE"), ev(2, 25, 4_000_000, "SALES")], ST) is not None


# ---------- API ----------

@pytest.fixture(autouse=True)
def no_graph(monkeypatch):
    """근거 검색은 US-07 테스트가 맡는다. 여기서는 Neo4j 없이 운영자금대출 약정서 조각(L01-1)만 근거로 돌려준다.
    문서 근거가 없으면 US-11에 따라 판단을 보류하므로, 대출 약정서는 red 픽스처에서 등록한다."""
    monkeypatch.setattr(response_service.evidence_service, "collect", doc_evidence("L01-1"))


def test_api_no_alert_no_plans(client):
    out = client.post("/api/response-plans").json()
    assert out["plans"] == [] and out["message"] == response_service.NO_ALERT


@pytest.fixture(scope="module")
def red(client):
    """register_sample: 11/25 운영자금대출 상환에서 -210만 원 부족, 11/28 정산 300만 원 입금."""
    register_sample(client)
    add_contract_doc("○○은행", "L01", "운영자금대출 약정서")
    return client.post("/api/forecasts", json={}).json()


def test_api_plans_ac01_ac02(client, red, monkeypatch):
    assert red["signal"] == "RED" and red["first_shortage_date"] == "2026-11-25"
    loan_event = next(d["cash_event_id"] for d in client.get(f"/api/alerts/{red['run_id']}/drivers").json()["drivers"] if d["label"].startswith("운영자금"))
    monkeypatch.setattr(response_service.evidence_service, "collect", lambda s, r: {"run_id": r.run_id, "message": None, "evidence": [
        {"id": "P1", "type": "GRAPH_PATH", "ref": f"event:{loan_event}", "text": "사업장 → 운영자금대출 → 11/25 상환"},
        {"id": "P2", "type": "GRAPH_PATH", "ref": "event:-1", "text": "관계없는 경로"},
        {"id": "D1", "type": "DOCUMENT_CHUNK", "ref": "L01-1", "text": "운영자금대출 약정서 지급 조건"}]})
    out = client.post("/api/response-plans").json()
    assert out["base"]["signal"] == "RED" and out["plans"]
    p = out["plans"][0]
    # 11/25 상환을 3일 뒤 11/28 정산 입금 뒤로 옮기면 4주 안에는 0원 아래로 내려가지 않는다 (안전 잔액 100만 원보다는 적어 노랑).
    # 이번 달 한 번만 옮기는 안이라 다음 달 12/25 상환에서는 다시 모자라고, 결과에 그대로 나온다.
    assert p["kind"] == "LOAN_CHECK" and p["parts"] == [{"due_date": "2026-11-28", "amount": 2_800_000}]
    assert p["result"]["signal"] == "YELLOW" and p["result"]["first_shortage_date"] == "2026-12-25" and len(p["result"]["daily"]) == 84
    assert [e["id"] for e in p["evidence"]] == ["P1", "D1"] and "(근거 P1, D1)" in p["description"] and not p["evidence_missing"]
    assert p["status"] == "PROPOSED"


def test_api_propose_does_not_apply_ac03(client, red):
    client.post("/api/response-plans")
    assert client.get("/api/alerts/current").json()["signal"] == "RED"
    loans = client.get("/api/loans").json()
    assert "2026-11-25" in loans[0]["next_due_dates"]


def test_api_plans_without_evidence_server(client, red, monkeypatch):
    def down(s, r):
        raise RuntimeError("neo4j down")
    monkeypatch.setattr(response_service.evidence_service, "collect", down)
    out = client.post("/api/response-plans").json()
    # US-11: 근거를 볼 수 없으면 계산 결과를 내보내지 않고 보류한다
    assert out["plans"] == [] and out["hold"]["code"] == "NO_EVIDENCE" and out["hold"]["missing"] == [response_service.SERVER_DOWN]


def test_api_approve_applies_and_survives_regeneration_ac03(client, red):
    out = client.post("/api/response-plans").json()
    pid = out["plans"][0]["plan_id"]
    r = client.post(f"/api/response-plans/{pid}/approve")
    assert r.status_code == 200
    assert r.json()["plan"]["status"] == "APPROVED" and r.json()["forecast"]["signal"] == "YELLOW"
    assert client.get("/api/alerts/current").json()["signal"] == "YELLOW"  # 대시보드 경보에 반영
    assert client.get("/api/loans").json()[0]["next_due_dates"][0] == "2026-11-28"
    # 같은 안·밀려난 안은 다시 승인할 수 없다
    assert client.post(f"/api/response-plans/{pid}/approve").status_code == 409
    # 다른 일정을 고쳐도 (예정 입출금 재생성) 승인한 안은 유지된다
    client.post("/api/forecasts", json={"base_date": "2026-11-01"})
    assert client.get("/api/loans").json()[0]["next_due_dates"][0] == "2026-11-28"
    assert [p["plan_id"] for p in client.get("/api/response-plans/approved").json()] == [pid]
    # 되돌리면 원래 일정과 빨강으로 돌아간다
    c = client.post(f"/api/response-plans/{pid}/cancel").json()
    assert c["plan"]["status"] == "CANCELLED" and c["forecast"]["signal"] == "RED"
    assert client.get("/api/loans").json()[0]["next_due_dates"][0] == "2026-11-25"


def test_api_stale_plan_conflict(client, red):
    out = client.post("/api/response-plans").json()
    pid = out["plans"][0]["plan_id"]
    loan = client.get("/api/loans").json()[0]
    body = {k: loan[k] for k in ("name", "lender", "principal", "interest_rate", "rate_type", "installment", "repay_day")}
    client.put(f"/api/loans/{loan['loan_id']}", json={**body, "installment": 2_900_000}).raise_for_status()
    r = client.post(f"/api/response-plans/{pid}/approve")
    assert r.status_code == 409 and "일정이 바뀌어" in r.json()["detail"]
    client.put(f"/api/loans/{loan['loan_id']}", json=body).raise_for_status()
    assert client.post("/api/response-plans/999999/approve").status_code == 404
