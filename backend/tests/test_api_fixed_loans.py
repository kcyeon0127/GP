"""US-02 API: AC-01·02 매월 지급 일정, AC-03 금액 0·지급일 누락, AC-04 분기 고정비."""


def test_fixed_cost_and_loan(client):
    r = client.post("/api/fixed-costs", json={"name": "임대료", "pay_cycle": "MONTHLY", "pay_day": 10, "amount": 1_500_000, "payee": "건물주"})
    assert r.status_code == 201 and r.json()["next_due_dates"] == ["2026-11-10", "2026-12-10", "2027-01-10"]
    r = client.post("/api/loans", json={"name": "운영자금대출", "lender": "○○은행", "principal": 60_000_000, "interest_rate": 5.1,
                                         "rate_type": "VARIABLE", "installment": 2_800_000, "repay_day": 25})
    assert r.status_code == 201 and r.json()["next_due_dates"] == ["2026-11-25", "2026-12-25"]


def test_missing_amount_and_day_422(client):
    bad = client.post("/api/fixed-costs", json={"name": "공과금", "pay_cycle": "MONTHLY", "amount": 0})
    assert bad.status_code == 422 and bad.json()["fields"] == ["amount", "pay_day"]


def test_quarterly_fixed_cost_month_end(client):
    r = client.post("/api/fixed-costs", json={"name": "화재보험료", "pay_cycle": "QUARTERLY", "pay_day": 31, "amount": 300_000})
    assert r.json()["next_due_dates"] == ["2026-12-31"]
