"""US-12 거래처 협의 메시지 초안. 기준일 11/1, 잔액·안전 잔액 100만 원 (conftest).

11/5 대성유통 매입 180만 원으로 부족, 11/8 청춘마켓 정산 400만 원.
"""
import pytest
from tests.helpers import add_contract_doc, doc_evidence

from app.services import response_service


@pytest.fixture(autouse=True)
def stub(monkeypatch):
    monkeypatch.setattr(response_service.evidence_service, "collect", doc_evidence("S01-1"))


@pytest.fixture(scope="module")
def setup(client):
    client.post("/api/counterparties", json={"name": "대성유통", "trade_type": "PURCHASE", "pay_cycle": "MONTHLY", "pay_day": 5, "amount": 1_800_000}).raise_for_status()
    client.post("/api/counterparties", json={"name": "청춘마켓", "trade_type": "SALES", "pay_cycle": "MONTHLY", "pay_day": 8, "amount": 4_000_000}).raise_for_status()
    add_contract_doc("대성유통", "S01", "대성유통 매입 계약서")


def _plan(client, kind):
    return next(p for p in client.post("/api/response-plans").json()["plans"] if p["kind"] == kind)


def test_draft_needs_approval_ac03(client, setup):
    p = _plan(client, "PURCHASE_SPLIT")
    r = client.post(f"/api/response-plans/{p['plan_id']}/draft")
    assert r.status_code == 409 and "승인한 대응안만" in r.json()["detail"]
    assert client.post("/api/response-plans/999999/draft").status_code == 404


def test_split_draft_matches_plan_ac01_ac04(client, setup):
    p = _plan(client, "PURCHASE_SPLIT")
    client.post(f"/api/response-plans/{p['plan_id']}/approve").raise_for_status()
    d = client.post(f"/api/response-plans/{p['plan_id']}/draft").json()
    assert d["to"] == "대성유통"
    (d0, a0), (d1, a1) = [(x["due_date"], x["amount"]) for x in p["parts"]]
    assert (d0, a0, d1, a1) == ("2026-11-05", 900_000, "2026-11-08", 900_000)
    # 초안 속 날짜·금액이 승인한 안과 같다
    assert "매입 대금 1,800,000원" in d["text"] and "900,000원은 예정대로 11월 5일" in d["text"] and "나머지 900,000원은 11월 8일" in d["text"]
    assert [f["value"] for f in d["facts"]][2:] == ["2026-11-05 900000", "2026-11-08 900000"]
    assert d["text"].startswith("대성유통 담당자님") and "드림" in d["text"]


def test_shift_draft_and_no_send_endpoint_ac02(client, setup):
    approved = client.get("/api/response-plans/approved").json()
    client.post(f"/api/response-plans/{approved[0]['plan_id']}/cancel").raise_for_status()
    p = _plan(client, "PAY_DATE_SHIFT")
    client.post(f"/api/response-plans/{p['plan_id']}/approve").raise_for_status()
    d = client.post(f"/api/response-plans/{p['plan_id']}/draft").json()
    assert "11월 5일에 드리기로 한 매입 대금 1,800,000원의 지급일을 11월 8일로 3일 미뤄" in d["text"]
    # 시스템이 대신 보내는 기능은 없다
    assert client.post(f"/api/response-plans/{p['plan_id']}/send").status_code in (404, 405)


def test_loan_draft_asks_bank(client, setup, monkeypatch):
    """은행에는 미뤄 달라는 부탁이 아니라 연체 없이 조정할 수 있는지 상담을 요청한다.
    11/5 매입은 앞 테스트에서 11/8로 옮겨져 있고, 11/6 대출 상환 280만 원으로 다시 부족해진다."""
    client.post("/api/loans", json={"name": "운영자금대출", "lender": "○○은행", "principal": 60_000_000, "interest_rate": 5.1,
                                    "rate_type": "VARIABLE", "installment": 2_800_000, "repay_day": 6}).raise_for_status()
    key = add_contract_doc("○○은행", "L01", "운영자금대출 약정서")
    monkeypatch.setattr(response_service.evidence_service, "collect", doc_evidence(key))
    p = next(p for p in client.post("/api/response-plans").json()["plans"] if p["kind"] == "LOAN_CHECK")
    client.post(f"/api/response-plans/{p['plan_id']}/approve").raise_for_status()
    d = client.post(f"/api/response-plans/{p['plan_id']}/draft").json()
    assert d["to"] == "○○은행"
    assert "11월 6일 상환 예정인 운영자금대출 상환 2,800,000원의 상환일을 11월 8일로" in d["text"] and "연체로 처리되지 않고" in d["text"]
