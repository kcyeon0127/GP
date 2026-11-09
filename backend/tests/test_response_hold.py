"""US-11 근거 부족 시 판단 보류. 시나리오를 순서대로 쌓아 가며 확인한다 (모듈 하나 = 빈 DB 하나).

기준일 11/1, 잔액·안전 잔액 100만 원 (conftest).
"""
import pytest
from tests.helpers import add_contract_doc, doc_evidence

from app.services import response_service

ONLY_PATH = lambda s, r: {"run_id": r.run_id, "message": None,  # noqa: E731
                          "evidence": [{"id": "P1", "type": "GRAPH_PATH", "ref": "event:-1", "text": "경로만 있는 근거"}]}


@pytest.fixture(autouse=True)
def stub(monkeypatch):
    monkeypatch.setattr(response_service.evidence_service, "collect", ONLY_PATH)


def _no_numbers(out):
    """AC-04: 보류할 때는 잔액 변화 같은 수치가 없다."""
    assert out["plans"] == [] and out["base"] == {"signal": out["base"]["signal"]}
    assert all("result" not in w and "description" not in w for w in out["withheld"])


def test_hold_when_nothing_comes_in_ac01(client):
    # 11/10 임대료 150만 원으로 부족하지만 그 뒤에 들어올 돈이 하나도 등록되지 않았다
    client.post("/api/fixed-costs", json={"name": "임대료", "pay_cycle": "MONTHLY", "pay_day": 10, "amount": 1_500_000, "payee": "건물주"}).raise_for_status()
    out = client.post("/api/response-plans").json()
    assert out["base"]["signal"] == "RED"
    assert out["hold"]["code"] == "NO_INFLOW" and out["hold"]["missing"] == [response_service.NEED_SALES]
    _no_numbers(out)


def test_hold_when_contract_has_no_document_ac01(client):
    # 정산 일정을 등록하면 옮길 날(11/15)은 생기지만, 건물주 임대차계약서가 없어 지급일 조정을 제시할 근거가 없다
    client.post("/api/counterparties", json={"name": "청춘마켓", "trade_type": "SALES", "pay_cycle": "MONTHLY", "pay_day": 15, "amount": 2_000_000}).raise_for_status()
    out = client.post("/api/response-plans").json()
    assert out["hold"]["code"] == "NO_EVIDENCE" and out["hold"]["missing"] == ["'건물주' 계약서가 등록되지 않았어요."]
    assert [w["kind"] for w in out["withheld"]] == ["EXPENSE_SHIFT"]
    _no_numbers(out)
    # 보류한 후보는 저장하지 않으므로 승인할 수 있는 안도 없다
    assert client.get("/api/response-plans/approved").json() == []


def test_resume_after_registering_document_ac02(client, monkeypatch):
    key = add_contract_doc("건물주", "R01", "상가 임대차계약서")
    monkeypatch.setattr(response_service.evidence_service, "collect", doc_evidence(key))
    out = client.post("/api/response-plans").json()
    assert out["hold"] is None and [p["kind"] for p in out["plans"]] == ["EXPENSE_SHIFT"]
    assert out["plans"][0]["parts"] == [{"due_date": "2026-11-15", "amount": 1_500_000}] and "D1" in out["plans"][0]["description"]


def test_document_without_matching_clause(client):
    # 계약서는 있는데 검색에서 조항이 나오지 않으면 그 문서를 짚어 알린다
    out = client.post("/api/response-plans").json()
    assert out["hold"]["missing"] == ["'상가 임대차계약서'에서 지급 조건 조항을 찾지 못했어요."]


def test_partial_shows_only_grounded_plans_ac03(client, monkeypatch):
    # 11/8 매입 대금이 늘어 후보가 여럿이 되지만, 문서가 있는 임대료 안만 제시하고 매입 안은 "근거 부족"으로 둔다
    client.post("/api/counterparties", json={"name": "대성유통", "trade_type": "PURCHASE", "pay_cycle": "MONTHLY", "pay_day": 8, "amount": 300_000}).raise_for_status()
    monkeypatch.setattr(response_service.evidence_service, "collect", doc_evidence("R01-1"))
    out = client.post("/api/response-plans").json()
    assert out["hold"] is None
    assert [p["kind"] for p in out["plans"]] == ["EXPENSE_SHIFT"]
    assert {w["kind"] for w in out["withheld"]} == {"PAY_DATE_SHIFT", "PURCHASE_SPLIT"}
    assert all(w["missing"] == "'대성유통' 계약서가 등록되지 않았어요." for w in out["withheld"])


def test_embedding_down_is_explained(client, monkeypatch):
    monkeypatch.setattr(response_service.evidence_service, "collect",
                        lambda s, r: {"run_id": r.run_id, "evidence": [], "message": response_service.evidence_service.DOCS_DOWN})
    out = client.post("/api/response-plans").json()
    assert out["hold"]["code"] == "NO_EVIDENCE" and out["hold"]["missing"] == [response_service.DOCS_SERVER_DOWN]
