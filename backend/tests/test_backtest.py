"""US-16 예측 정확도 백테스트: 실제 잔액 복원, 판정(적중·오경보·놓침·정상), 지표 (T8·T9)."""
from datetime import date, timedelta
from pathlib import Path

from app.domain import backtest as bt
from app.domain import transactions as tx

SAMPLE = Path(__file__).resolve().parents[1] / "data" / "sample_bank_transactions.csv"


def test_actual_daily_uses_last_balance_of_day_and_carries_forward():
    t = tx.parse_csv("거래일자,내용,출금액,입금액,거래후잔액\n2026-10-01,a,100,,900\n2026-10-01,b,,50,950\n2026-10-03,c,,50,1000\n")
    assert bt.actual_daily(t) == {date(2026, 10, 1): 950, date(2026, 10, 2): 950, date(2026, 10, 3): 1000}


def _monthly_file(months=4, rent_day=10, pay_in=2_500_000, rent=2_500_000, start=1_000_000):
    """매월 5일 +250만, 10일 -250만만 있는 가게 (잔액 100만↔350만). 예측이 정확하면 오차 0이어야 한다."""
    rows, bal, d = [], start, date(2026, 6, 1)
    while d < date(2026, 6, 1) + timedelta(days=30 * months):
        if d.day == 5:
            bal += pay_in
            rows.append(f"{d},한빛식자재,,{pay_in},{bal}")
        if d.day == rent_day:
            bal -= rent
            rows.append(f"{d},임대료,{rent},,{bal}")
        d += timedelta(days=1)
    return tx.parse_csv("거래일자,내용,출금액,입금액,거래후잔액\n" + "\n".join(rows) + "\n")


def test_perfect_schedule_has_zero_error():
    points = bt.run(_monthly_file(), safe_balance=0)
    assert points and all(p.mae == 0 and p.outcome == "OK" for p in points)


def test_hit_when_both_alert_and_error_days():
    points = bt.run(_monthly_file(), safe_balance=2_000_000)
    assert points and all(p.outcome == "HIT" and p.alert_error_days == 0 for p in points)
    s = bt.summary(points)
    assert s["hit_rate"] == 1.0 and s["false_alarm_rate"] == 0.0 and s["mae_mean"] == 0


def test_summary_counts_false_alarm_and_miss():
    p = lambda o: bt.Point(date(2026, 10, 1), 1, None, None, o, None, 100)  # noqa: E731
    s = bt.summary([p("HIT"), p("FALSE_ALARM"), p("MISS"), p("OK")])
    assert (s["hit"], s["false_alarm"], s["miss"], s["ok"]) == (1, 1, 1, 1) and s["hit_rate"] == 0.5 and s["false_alarm_rate"] == 0.5


def test_sample_runs_and_irregular_average_reduces_error():
    t = tx.parse_csv(SAMPLE.read_text(encoding="utf-8-sig"))
    plain, with_avg = bt.summary(bt.run(t, 2_000_000)), bt.summary(bt.run(t, 2_000_000, irregular=True))
    assert plain["runs"] >= 1 and with_avg["mae_mean"] < plain["mae_mean"]  # 카드 매출처럼 비정기 입금이 빠진 만큼 오차가 크다


def test_too_short_file_has_no_points():
    assert bt.run(_monthly_file(months=1), 0) == []
