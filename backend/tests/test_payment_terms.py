"""US-14 결제조건 자동 추정: 추정 모듈(T1), 추정 API(T2), 확정 저장·재계산(T4)."""
from datetime import date
from pathlib import Path

from app.domain import payment_terms as pt
from app.domain import transactions as tx

SAMPLE = Path(__file__).resolve().parents[1] / "data" / "sample_bank_transactions.csv"
HEADER = "거래일자,내용,출금액,입금액,거래후잔액\n"


def _txns(*rows):
    return tx.parse_csv(HEADER + "".join(f"{d},{n},,{a},{i}\n" for i, (d, n, a) in enumerate(rows, 1)))


def test_registered_delay_is_measured_from_promised_day():
    t = _txns(("2026-08-10", "한빛식자재", 3_000_000), ("2026-09-07", "한빛식자재", 3_000_000), ("2026-10-14", "한빛식자재", 3_000_000))
    [e] = pt.estimate(t, [pt.Registered(1, "한빛식자재", "MONTHLY", 7)])
    assert (e.status, e.counterparty_id, e.pay_cycle, e.pay_day) == ("ESTIMATED", 1, "MONTHLY", 7)
    assert e.delays == [3, 0, 7] and e.avg_delay_days == 3 and e.max_delay_days == 7


def test_early_payment_counts_as_zero_delay():
    t = _txns(("2026-08-05", "새봄마트", 1_000_000), ("2026-09-15", "새봄마트", 1_000_000), ("2026-10-17", "새봄마트", 1_000_000))
    [e] = pt.estimate(t, [pt.Registered(2, "새봄마트", "MONTHLY", 15)])
    assert e.delays == [-10, 0, 2] and e.avg_delay_days == 1  # 일찍 온 날은 0일로 센다


def test_month_boundary_belongs_to_previous_promise():
    t = _txns(("2026-09-02", "청춘마켓", 500_000), ("2026-10-03", "청춘마켓", 500_000), ("2026-11-01", "청춘마켓", 500_000))
    [e] = pt.estimate(t, [pt.Registered(3, "청춘마켓", "MONTHLY", 28)])
    assert e.delays == [5, 5, 4]  # 다음 달 초 입금은 지난달 28일 약속분이 늦게 온 것


def test_less_than_three_is_not_estimated():
    [e] = pt.estimate(_txns(("2026-09-07", "우리상회", 1), ("2026-10-07", "우리상회", 1)))
    assert e.status == "INSUFFICIENT" and e.pay_day is None and "3건" in e.basis


def test_unregistered_estimates_day_and_delay():
    t = _txns(*[(f"2026-{m:02d}-{d:02d}", "(주)해든푸드", 2_000_000) for m, d in ((6, 10), (7, 10), (8, 12), (9, 16), (10, 10))])
    [e] = pt.estimate(t, [pt.Registered(5, "해든푸드", "MONTHLY", 10)])  # 법인 표기가 달라도 등록 거래처와 맞춘다
    assert e.counterparty_id == 5 and e.name == "해든푸드"
    [u] = pt.estimate(t)
    assert (u.pay_day, u.avg_delay_days, u.max_delay_days) == (10, 2, 6)  # 0,0,2,6,0일 → 평균 1.6일


def test_daily_card_sales_are_not_counterparties():
    found = {e.name for e in pt.estimate(tx.parse_csv(SAMPLE.read_text(encoding="utf-8-sig")))}
    assert "카드매출 입금" not in found and {"한빛식자재", "새봄마트"} <= found


def test_irregular_interval():
    t = _txns(("2026-06-01", "들쭉상회", 1), ("2026-06-15", "들쭉상회", 1), ("2026-08-20", "들쭉상회", 1))
    [e] = pt.estimate(t)
    assert e.status == "IRREGULAR"


def test_api_estimate_and_confirm_recalculates(client):
    cid = client.post("/api/counterparties", json={"name": "한빛식자재", "trade_type": "SALES", "pay_cycle": "MONTHLY", "pay_day": 5, "amount": 3_200_000}).json()["counterparty_id"]
    body = client.post("/api/payment-terms/estimate", json={"text": SAMPLE.read_text(encoding="utf-8-sig")}).json()
    est = next(e for e in body["estimates"] if e["name"] == "한빛식자재")
    assert est["counterparty_id"] == cid and est["registered"] == {"pay_cycle": "MONTHLY", "pay_day": 5} and est["avg_delay_days"] == 2
    assert est["confirmed_delay_days"] is None
    r = client.put(f"/api/payment-terms/{cid}", json={"pay_day": 7, "delay_days": 0, "sample_count": est["count"]})
    assert r.status_code == 200 and r.json()["pay_day"] == 7 and r.json()["forecast"]["run_id"]
    cp = next(c for c in client.get("/api/counterparties").json() if c["counterparty_id"] == cid)
    assert cp["pay_day"] == 7 and all(date.fromisoformat(d).day == 7 for d in cp["next_due_dates"])
    assert client.get("/api/payment-terms").json()[0]["delay_days"] == 0
    assert client.put(f"/api/payment-terms/{cid}", json={"delay_days": 61, "sample_count": 3}).status_code == 422
    assert client.put("/api/payment-terms/987654321", json={"delay_days": 1, "sample_count": 3}).status_code == 404
