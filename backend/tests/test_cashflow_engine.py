"""T10·T13·T14·T16: CashflowEngine을 기준 정답 20건(tests/fixtures/cashflow)과 비교한다."""
import csv
from collections import defaultdict
from datetime import date
from pathlib import Path

import pytest

from app.domain.cashflow_engine import forecast
from app.domain.enums import SignalLevel

FIX = Path(__file__).parent / "fixtures" / "cashflow"


def _read(name):
    with open(FIX / name, encoding="utf-8") as f:
        return list(csv.DictReader(f))


CASES = {r["case_id"]: r for r in _read("cases.csv")}
EVENTS = defaultdict(list)
for r in _read("events.csv"):
    EVENTS[r["case_id"]].append((date.fromisoformat(r["date"]), int(r["amount"]) * (1 if r["direction"] == "IN" else -1)))
DAILY = defaultdict(list)
for r in _read("expected_daily.csv"):
    DAILY[r["case_id"]].append((date.fromisoformat(r["date"]), int(r["balance"])))
SUMMARY = {r["case_id"]: r for r in _read("expected_summary.csv")}


def run(cid):
    c = CASES[cid]
    return forecast(date.fromisoformat(c["base_date"]), int(c["start_balance"]), int(c["safe_balance"]), EVENTS[cid])


def opt_date(s):
    return date.fromisoformat(s) if s else None


def opt_int(s):
    return int(s) if s else None


@pytest.mark.parametrize("cid", sorted(CASES))
def test_daily_balance_matches_reference(cid):
    """US-03 AC-02: 날짜별 잔액 84일이 정답과 일치."""
    assert run(cid).daily == DAILY[cid]


@pytest.mark.parametrize("cid", sorted(CASES))
def test_first_shortage_and_signal_match_reference(cid):
    """US-04 AC-03, US-05: 최초 부족일·부족액·신호가 정답과 일치."""
    f, s = run(cid), SUMMARY[cid]
    assert f.first_shortage_date == opt_date(s["first_short_date"])
    assert f.shortage_amount == opt_int(s["short_amount"])
    assert f.max_shortage_amount == opt_int(s["max_short_amount"])
    assert (f.min_balance, f.min_balance_date) == (int(s["min_balance"]), date.fromisoformat(s["min_balance_date"]))
    assert f.signal.value == s["signal"]
    assert f.first_below_safe_date == opt_date(s["first_below_safe_date"])


def test_same_input_same_result():
    """US-03 AC-03: 같은 입력을 반복 계산하면 결과가 같다."""
    assert all(run("C18") == run("C18") for _ in range(5))


def test_us04_ac01_shortage_1125_2_1m():
    f = run("C03")
    assert (f.first_shortage_date, f.shortage_amount) == (date(2026, 11, 25), 2_100_000)


def test_us04_ac02_no_shortage():
    assert run("C02").first_shortage_date is None


def test_signal_red_yellow_green():
    """T16: 빨강·노랑·초록 판정 3건 (US-05 AC-01~03)."""
    assert run("C03").signal == SignalLevel.RED
    assert run("C01").signal == SignalLevel.GREEN
    yellow = run("C04")
    assert yellow.signal == SignalLevel.YELLOW and yellow.first_below_safe_date == date(2026, 11, 18)
