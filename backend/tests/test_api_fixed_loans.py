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


def _counts():
    from sqlalchemy import text

    from app.db import engine

    with engine.connect() as c:
        return c.execute(text("select count(*) from counterparty")).scalar(), c.execute(text("select count(*) from contract")).scalar()


def test_bad_quarter_months_422_and_normalized(client):
    bad = client.post("/api/fixed-costs", json={"name": "보험료", "pay_cycle": "QUARTERLY", "pay_day": 31, "months": "13,abc", "amount": 300_000})
    assert bad.status_code == 422 and bad.json()["fields"] == ["months"]
    ok = client.post("/api/fixed-costs", json={"name": "보험료", "pay_cycle": "QUARTERLY", "pay_day": 31, "months": "12, 3", "amount": 300_000}).json()
    assert ok["months"] == "3,12" and ok["next_due_dates"] == ["2026-12-31"]


def test_payee_change_and_delete_cleanup(client):
    before = _counts()
    f = client.post("/api/fixed-costs", json={"name": "관리비", "pay_cycle": "MONTHLY", "pay_day": 20, "amount": 200_000, "payee": "관리사무소"}).json()
    assert _counts() == (before[0] + 1, before[1] + 1)
    r = client.put(f"/api/fixed-costs/{f['fixed_cost_id']}", json={"name": "관리비", "pay_cycle": "MONTHLY", "pay_day": 20, "amount": 250_000, "payee": "새 관리회사"})
    assert r.json()["payee"] == "새 관리회사" and _counts() == (before[0] + 1, before[1] + 1)  # 이전 받는 곳은 정리된다
    client.delete(f"/api/fixed-costs/{f['fixed_cost_id']}")
    assert _counts() == before


def test_loan_delete_cleanup(client):
    before = _counts()
    l = client.post("/api/loans", json={"name": "시설자금", "lender": "△△은행", "principal": 1, "interest_rate": 3, "installment": 900_000, "repay_day": 25}).json()
    client.delete(f"/api/loans/{l['loan_id']}")
    assert _counts() == before
