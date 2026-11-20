"""US-18 D 말로 물어보기: 규칙 파서, LLM 계획 검증, POST /api/ask 폴백 경로. 기준일 11/1 (conftest)."""
import json

import pytest
from tests.helpers import register_sample

from app.domain import ask_rules as ar
from app.repositories import graph_repository, llm_client

SALES = ["청춘마켓", "한빛식자재"]


@pytest.fixture(scope="module", autouse=True)
def cleanup_graph(client):
    yield
    graph_repository.query("MATCH (n {business_id: 999}) DETACH DELETE n")


@pytest.mark.parametrize("q,delay,rev,cost,rate", [
    ("한빛식자재 정산이 2주 밀리면 대출 갚을 수 있어?", ("한빛식자재", 14), None, None, None),
    ("청춘마켓 입금이 10일 늦어지고 매출이 15% 줄면?", ("청춘마켓", 10), 15, None, None),
    ("다음 달 매출이 줄면 어떻게 돼?", None, 20, None, None),
    ("원가가 8% 오르면?", None, None, 8, None),
    ("금리가 50bp 오르면 상환 부담은?", None, None, None, 0.5),
])
def test_rule_plan(q, delay, rev, cost, rate):
    p = ar.rule_plan(q, SALES, ["대성유통"], has_variable_loan=True)
    assert (p.delay, p.revenue_drop_pct, p.cost_rise_pct, p.rate_rise_pp) == (delay, rev, cost, rate)
    assert p.problems == []


def test_rule_plan_problems():
    assert ar.rule_plan("정산이 밀리면?", SALES, [], True).problems[0].startswith("어느 매출처")
    assert "신규 대출" in ar.rule_plan("500만원 정책대출을 받으면?", SALES, [], True).problems[0]
    assert "폐업" in ar.rule_plan("청춘마켓이 폐업하면?", SALES, [], True).problems[0]
    assert ar.rule_plan("안녕하세요", SALES, [], True).problems == [ar.NO_CONDITION]
    assert "90%" in ar.rule_plan("매출이 95% 줄면?", SALES, [], True).problems[0]


GOOD = {"settlement_delay": {"counterparty": "한빛식자재", "days": 14}, "revenue_drop_pct": None, "cost_rise_pct": None, "rate_rise_pp": None, "unsupported": []}
Q = "한빛식자재 정산이 2주 밀리면?"


def test_validate_llm_accepts_good_plan():
    p = ar.validate_llm(GOOD, Q, SALES, True)
    assert p.delay == ("한빛식자재", 14) and p.problems == []


@pytest.mark.parametrize("obj,q", [
    ({**GOOD, "settlement_delay": {"counterparty": "없는가게", "days": 14}}, Q),  # 등록되지 않은 이름
    ({**GOOD, "settlement_delay": {"counterparty": "청춘마켓", "days": 14}}, Q),  # 질문에 없는 매출처
    ({**GOOD, "settlement_delay": {"counterparty": "한빛식자재", "days": 90}}, Q),  # 범위 밖
    ({**GOOD, "settlement_delay": {"counterparty": "한빛식자재", "days": True}}, Q),  # 타입
    ({**GOOD, "revenue_drop_pct": 20}, Q),  # 질문에 매출 얘기가 없다
    ({**GOOD, "extra": 1}, Q),  # 모르는 키
    ({"settlement_delay": None, "unsupported": []}, Q),  # 조건 없음
])
def test_validate_llm_rejects(obj, q):
    with pytest.raises(ar.PlanRejected):
        ar.validate_llm(obj, q, SALES, True)


def test_parse_llm_json_strips_fences():
    assert ar.parse_llm_json('```json\n{"rate_rise_pp": 1}\n```') == {"rate_rise_pp": 1}
    with pytest.raises(ar.PlanRejected):
        ar.parse_llm_json("모르겠어요")


def fake_llm(plan: dict | str, text: str = "정산이 늦어지면 잔액이 모자라요 [C1]."):
    def chat(messages, **k):
        if k.get("json_mode"):
            return plan if isinstance(plan, str) else json.dumps(plan, ensure_ascii=False)
        return text
    return chat


def test_ask_rule_fallback_when_llm_down(client):
    register_sample(client)
    out = client.post("/api/ask", json={"query": "한빛식자재 정산이 2주 밀리면 대출 갚을 수 있어?"}).json()
    assert out["plan"]["source"] == "rule" and out["plan"]["fallback_reason"] == "LLM_DOWN"
    assert out["plan"]["conditions"]["settlement_delay"] == {"counterparty": "한빛식자재", "days": 14}
    assert out["plan"]["described"] == ["한빛식자재 정산 14일 지연"]
    assert out["result"]["scenario"]["min_balance"] <= out["result"]["base"]["min_balance"]
    assert out["evidence"][0]["id"] == "P1" and any("한빛식자재 매출 계약" in e["text"] for e in out["evidence"])
    e = out["explanation"]
    assert e["source"] == "template" and e["fallback_reason"] == "LLM_DOWN" and e["verified"] and "[C1]" in e["text"]
    assert out["confidence"]["level"] in ("HIGH", "MEDIUM", "LOW") and out["scenario_id"]


def test_ask_llm_plan_and_explanation(client, monkeypatch):
    monkeypatch.setattr(llm_client, "chat", fake_llm(GOOD))
    out = client.post("/api/ask", json={"query": Q}).json()
    assert out["plan"]["source"] == "llm" and out["plan"]["fallback_reason"] is None
    if out["confidence"]["level"] != "LOW":
        assert out["explanation"]["source"] == "llm" and out["explanation"]["cited_ids"] == ["C1"]


def test_ask_llm_hallucinated_name_falls_back_to_rule(client, monkeypatch):
    monkeypatch.setattr(llm_client, "chat", fake_llm({**GOOD, "settlement_delay": {"counterparty": "대박상회", "days": 14}},
                                                     text="11/30에 999,999원이 모자라요 [C1]."))
    out = client.post("/api/ask", json={"query": Q}).json()
    assert out["plan"]["source"] == "rule" and out["plan"]["fallback_reason"] == "VERIFY_FAILED"
    assert out["plan"]["conditions"]["settlement_delay"]["counterparty"] == "한빛식자재"
    if out["confidence"]["level"] != "LOW":  # 새 숫자를 지어낸 설명은 템플릿으로 바뀐다
        assert out["explanation"]["source"] == "template" and out["explanation"]["fallback_reason"] == "VERIFY_FAILED"


def test_ask_broken_json_falls_back(client, monkeypatch):
    monkeypatch.setattr(llm_client, "chat", fake_llm("조건은 정산 지연입니다"))
    out = client.post("/api/ask", json={"query": "금리가 1%p 오르면?"}).json()
    assert out["plan"]["source"] == "rule" and out["plan"]["conditions"]["rate_rise_pp"] == 1


def test_ask_nothing_to_simulate(client):
    out = client.post("/api/ask", json={"query": "오늘 날씨 어때?"}).json()
    assert out["result"] is None and out["plan"]["problems"] == [ar.NO_CONDITION] and out["message"]


def test_ask_validation(client):
    assert client.post("/api/ask", json={"query": ""}).status_code == 422
