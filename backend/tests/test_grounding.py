"""US-18 근거 인용 설명: 검증기(순수 함수)와 explain_service 폴백. LLM은 llm_client.chat 대역으로 바꾼다."""
from datetime import date

import pytest

from app.domain import grounding
from app.repositories import llm_client
from app.services import explain_service as ex

EVIDENCE = [
    {"id": "P1", "type": "GRAPH_PATH", "text": "사업장 → 임대료 → 11/10 임대료 1,500,000원 (경보일 전에 나가는 돈)"},
    {"id": "P2", "type": "GRAPH_PATH", "text": "한빛식자재 매출 계약 → 11/28 한빛식자재 정산 3,000,000원 (경보일 뒤에 들어오는 돈)"},
    {"id": "D1", "type": "DOCUMENT_CHUNK", "text": "임대차계약서 지급 조건"},
]
FACTS = [ex.Fact("최초 부족일", date(2026, 11, 10), "date"), ex.Fact("부족액", 500_000), ex.Fact("12주 최저 잔액", -1_520_000)]
TEMPLATE = ["11/10에 500,000원이 부족해요 [C1].", "영향 일정은 경로로 확인했어요 [P1][P2]."]


def _llm(text):
    return lambda *a, **k: text


def _down(*a, **k):
    raise llm_client.LLMUnavailable("ConnectError")


def run(monkeypatch, reply):
    monkeypatch.setattr(llm_client, "chat", reply if callable(reply) else _llm(reply))
    return ex.explain("왜 경보가 났나요", EVIDENCE, FACTS, TEMPLATE)


def test_good_answer_passes(monkeypatch):
    out = run(monkeypatch, "11월 10일에 잔액이 0원 아래로 내려가 50만 원이 모자라요 [C1]. 11/10 임대료 1,500,000원이 먼저 나가기 때문이에요 [P1].\n"
                           "11/28 정산 3,000,000원은 그 뒤에 들어와요. [P2]")
    assert out["source"] == "llm" and out["verified"] and out["fallback_reason"] is None
    assert out["cited_ids"] == ["C1", "P1", "P2"]


def test_rounded_amount_with_unit_passes(monkeypatch):
    # -1,520,000원을 '152만 원'으로 줄여 쓴 것은 같은 숫자로 본다
    out = run(monkeypatch, "12주 최저 잔액은 약 -152만 원이에요 [C1].")
    assert out["source"] == "llm"


@pytest.mark.parametrize("reply,problem", [
    ("11/10에 500,000원이 부족해요 [P9].", "없는 근거 ID P9"),
    ("11/10에 700,000원이 부족해요 [C1].", "근거에 없는 숫자 700,000원"),
    ("11/12에 500,000원이 부족해요 [C1].", "근거에 없는 숫자 11/12"),
    ("매출이 10% 줄었어요 [C1].", "근거에 없는 숫자 10%"),
    ("11/10에 500,000원이 부족해요 [C1]. 임대료 때문이에요.", "2번째 문장에 근거 ID 없음"),
    ("余额不足 [C1].", "한국어가 아닌 응답"),
])
def test_bad_answer_falls_back_to_template(monkeypatch, reply, problem):
    out = run(monkeypatch, reply)
    assert out["source"] == "template" and out["fallback_reason"] == "VERIFY_FAILED"
    assert any(problem in p for p in out["problems"]), out["problems"]
    assert out["text"] == " ".join(TEMPLATE) and out["verified"]  # 템플릿도 같은 검증을 통과한다


def test_server_down_uses_template(monkeypatch):
    out = run(monkeypatch, _down)
    assert out["source"] == "template" and out["fallback_reason"] == "LLM_DOWN" and out["fallback_ko"] == "AI 서버 꺼짐"


def test_calc_evidence_lists_facts():
    c = ex.calc_evidence(FACTS)
    assert c["id"] == "C1" and "11/10" in c["text"] and "500,000원" in c["text"] and "-1,520,000원" in c["text"]


def test_split_merges_trailing_citation_and_strips_bullets():
    assert grounding.split_sentences("- 모자라요.\n[P1]\n2. 들어와요 [P2].") == ["모자라요. [P1]", "들어와요 [P2]."]


def test_extract_numbers():
    n = grounding.extract("2026-11-07 기준, 11월 10일 1억 2,000만 원과 3.5% 그리고 1,500,000")
    assert n.dates == {(11, 7), (11, 10)} and n.pct == {3.5}
    assert {v for v, _ in n.won} == {120_000_000, 1_500_000}


def test_llm_client_errors(monkeypatch):
    import httpx

    def refused(*a, **k):
        raise httpx.ConnectError("refused")
    monkeypatch.setattr(httpx, "post", refused)
    with pytest.raises(llm_client.LLMUnavailable):
        llm_client.chat([{"role": "user", "content": "x"}])

    class Bad:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": []}
    monkeypatch.setattr(httpx, "post", lambda *a, **k: Bad())
    with pytest.raises(llm_client.LLMError):
        llm_client.chat([{"role": "user", "content": "x"}])
