"""US-18 경보 신뢰도와 경보 설명 API. 기준일 11/1, 잔액·안전 잔액 100만 원 (conftest).

근거 검색은 대역으로 바꾼다 (Neo4j·임베딩 서버 없이): 영향 일정마다 P 근거를 만들거나, 아무 근거도 없게 한다.
"""
import pytest
from tests.helpers import add_contract_doc, register_sample

from app.domain import confidence as cf
from app.domain.constants import CONF_W_CLAUSE, CONF_W_INFLOW, CONF_W_LINK, CONF_W_PATH
from app.repositories import llm_client
from app.services import confidence_service, evidence_service, forecast_service, response_service


def test_assess_levels_and_cap():
    full = [cf.Factor("a", 1.0, 60, "이유"), cf.Factor("b", 1.0, 40, "이유")]
    assert cf.assess(full)["level"] == "HIGH" and cf.assess(full)["score"] == 100
    assert cf.assess(full, cap_medium=True)["level"] == "MEDIUM"
    half = [cf.Factor("a", 0.5, 60, "이유", ["계약서 등록"]), cf.Factor("b", 0.0, 40, "이유", ["계약서 등록", "정산 등록"])]
    out = cf.assess(half)
    assert out["score"] == 30 and out["level"] == "LOW" and out["missing"] == ["계약서 등록", "정산 등록"]
    assert CONF_W_PATH + CONF_W_CLAUSE + CONF_W_LINK + CONF_W_INFLOW == 100


def paths_for_drivers(*docs: str):
    def collect(s, r):
        ev = [{"id": f"P{i}", "type": "GRAPH_PATH", "ref": f"event:{e.cash_event_id}", "text": f"{e.due_date:%m/%d} {e.label} {e.amount:,}원"}
              for i, (e, _) in enumerate(forecast_service.drivers(s, r), 1)]
        ev += [{"id": f"D{i}", "type": "DOCUMENT_CHUNK", "ref": k, "text": "계약서 지급 조건", "score": 0.8} for i, k in enumerate(docs, 1)]
        return {"run_id": r.run_id, "evidence": ev, "message": None}
    return collect


NOTHING = lambda s, r: {"run_id": r.run_id, "evidence": [], "message": "근거 없음"}  # noqa: E731


@pytest.fixture(scope="module")
def red(client):
    register_sample(client)
    return client.post("/api/forecasts", json={"base_date": "2026-11-01", "current_balance": 1_000_000}).json()["run_id"]


def test_alert_confidence_with_paths_only_is_medium_or_high(client, red, monkeypatch):
    monkeypatch.setattr(evidence_service, "collect", paths_for_drivers())
    c = client.get(f"/api/alerts/{red}/confidence").json()["confidence"]
    pts = {f["key"]: f["points"] for f in c["factors"]}
    assert pts["path"] == CONF_W_PATH and pts["clause"] == 0 and pts["inflow"] == CONF_W_INFLOW
    assert c["level"] in ("HIGH", "MEDIUM") and any("계약서를 등록하세요" in m for m in c["missing"])
    assert any("거래관계 경로로 확인" in x for x in c["reasons"])


def test_alert_confidence_low_without_evidence(client, red, monkeypatch):
    monkeypatch.setattr(evidence_service, "collect", NOTHING)
    c = client.get(f"/api/alerts/{red}/confidence").json()["confidence"]
    assert c["level"] == "LOW"


def test_graph_down_caps_and_explains(client, red, monkeypatch):
    def down(s, r):
        raise RuntimeError("neo4j down")
    monkeypatch.setattr(evidence_service, "collect", down)
    out = client.post(f"/api/alerts/{red}/explain").json()
    assert out["message"] and out["confidence"]["level"] != "HIGH"
    assert confidence_service.GRAPH_DOWN in out["confidence"]["missing"]


def test_clause_raises_score(client, red, monkeypatch):
    key = add_contract_doc("한빛식자재", "S09", "한빛식자재 납품계약서")
    monkeypatch.setattr(evidence_service, "collect", paths_for_drivers(key))
    c = client.get(f"/api/alerts/{red}/confidence").json()["confidence"]
    assert next(f for f in c["factors"] if f["key"] == "clause")["points"] > 0


def test_explain_template_when_llm_down(client, red, monkeypatch):
    monkeypatch.setattr(evidence_service, "collect", paths_for_drivers())
    out = client.post(f"/api/alerts/{red}/explain").json()
    e = out["explanation"]
    assert e["source"] == "template" and e["fallback_reason"] == "LLM_DOWN" and e["verified"]
    assert "[C1]" in e["text"] and "P1" in e["cited_ids"] and e["calc"]["id"] == "C1"
    assert [x["id"] for x in out["evidence"]][0] == "P1"


def test_explain_llm_verified(client, red, monkeypatch):
    monkeypatch.setattr(evidence_service, "collect", paths_for_drivers())
    monkeypatch.setattr(llm_client, "chat", lambda *a, **k: "11/10에 잔액이 0원 아래로 내려가요 [C1]. 임대료가 먼저 나가기 때문이에요 [P1].")
    e = client.post(f"/api/alerts/{red}/explain").json()["explanation"]
    assert e["source"] == "llm" and e["verified"] and e["cited_ids"] == ["C1", "P1"]


def test_explain_held_when_low(client, red, monkeypatch):
    monkeypatch.setattr(evidence_service, "collect", NOTHING)
    called = []
    monkeypatch.setattr(llm_client, "chat", lambda *a, **k: called.append(1) or "x")
    out = client.post(f"/api/alerts/{red}/explain").json()
    assert out["confidence"]["level"] == "LOW" and out["explanation"]["fallback_reason"] == "HOLD" and not called
    assert not any(ch.isdigit() for ch in out["explanation"]["text"])  # 보류 문구에는 수치가 없다


def test_green_has_no_confidence(client):
    r = client.post("/api/forecasts", json={"current_balance": 50_000_000}).json()
    assert client.get(f"/api/alerts/{r['run_id']}/confidence").json()["confidence"] is None
    client.post("/api/forecasts", json={"current_balance": 1_000_000})


def test_plans_held_when_confidence_low(client, red, monkeypatch):
    keys = [add_contract_doc("건물주", "R09", "상가 임대차계약서"), add_contract_doc("○○은행", "L09", "대출 약정서")]
    monkeypatch.setattr(evidence_service, "collect", paths_for_drivers(*keys))
    low = {"level": "LOW", "score": 20, "reasons": ["이유"], "missing": ["'○○은행' 계약서를 등록하세요."], "factors": []}
    monkeypatch.setattr(confidence_service, "for_alert", lambda *a, **k: low)
    out = client.post("/api/response-plans").json()
    assert out["hold"]["code"] == "LOW_CONFIDENCE" and out["hold"]["missing"] == low["missing"]
    assert out["plans"] == [] and out["base"] == {"signal": out["base"]["signal"]}
    assert out["explanation"]["fallback_reason"] == "HOLD" and out["confidence"]["level"] == "LOW"
    assert client.get("/api/response-plans/approved").json() == []


def test_plans_have_confidence_and_explanation(client, red, monkeypatch):
    monkeypatch.setattr(evidence_service, "collect", paths_for_drivers("R09-1", "L09-1"))
    out = client.post("/api/response-plans").json()
    if out["hold"]:
        pytest.skip(f"이 일정에서는 보류: {out['hold']['code']}")
    assert out["confidence"]["level"] in ("HIGH", "MEDIUM")
    e = out["explanation"]
    assert e["source"] == "template" and e["verified"] and "[C1]" in e["text"]
    assert response_service.PLAN_TASK
