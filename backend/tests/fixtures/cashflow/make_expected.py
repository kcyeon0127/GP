"""T9 기준 정답 생성기. 앱 코드(CashflowEngine)와 따로 만든 참고 구현이다.

계산 규칙 (양식 6 무결성 규칙 4·5·6):
- 구간은 기준일부터 84일(기준일 = 1일째). 구간 밖 일정은 무시한다.
- 일별 잔액 = 시작 잔액 + 그날까지의 입출금 합계. 같은 날 일정은 순서와 상관없이 하루 합계로 반영한다.
- 최초 부족일 = 일별 잔액이 처음 0원 미만인 날, 부족액 = 그날 잔액의 절댓값.
- 신호(1~28일째): 0원 미만이 있으면 RED, 안전 잔액 미만이 있으면 YELLOW, 아니면 GREEN.

실행: python make_expected.py  →  같은 폴더에 CSV 4개를 다시 쓴다.
"""
import csv
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

from cases import CASES, daily_sales_events

HORIZON = 84
WINDOW = 28
HERE = Path(__file__).parent


def events_of(case):
    return daily_sales_events(case["base"]) if case["events"] == "DAILY_SALES" else case["events"]


def compute(case):
    base = date.fromisoformat(case["base"])
    net = defaultdict(int)
    for day, amount, _ in events_of(case):
        offset = (date.fromisoformat(day) - base).days
        if 0 <= offset < HORIZON:
            net[offset] += amount
    bal, daily = case["start"], []
    for i in range(HORIZON):
        bal += net[i]
        daily.append((base + timedelta(days=i), bal))
    first_short = next(((dt, -b) for dt, b in daily if b < 0), None)
    lo_date, lo = min(daily, key=lambda x: x[1])  # 같은 최저값이면 앞선 날
    win = daily[:WINDOW]
    if any(b < 0 for _, b in win):
        signal = "RED"
    elif any(b < case["safe"] for _, b in win):
        signal = "YELLOW"
    else:
        signal = "GREEN"
    below_safe = next((dt for dt, b in win if b < case["safe"]), None)
    return daily, dict(
        first_short_date=first_short[0].isoformat() if first_short else "",
        short_amount=first_short[1] if first_short else "",
        max_short_amount=max(0, -lo) or "",
        min_balance=lo,
        min_balance_date=lo_date.isoformat(),
        signal=signal,
        first_below_safe_date=below_safe.isoformat() if below_safe else "",
    )


def main():
    w = lambda name: csv.writer(open(HERE / name, "w", newline="", encoding="utf-8"))
    cases, events, daily_out, summary = w("cases.csv"), w("events.csv"), w("expected_daily.csv"), w("expected_summary.csv")
    cases.writerow(["case_id", "title", "base_date", "start_balance", "safe_balance", "note"])
    events.writerow(["case_id", "event_id", "date", "direction", "amount", "label"])
    daily_out.writerow(["case_id", "day", "date", "balance"])
    cols = ["first_short_date", "short_amount", "max_short_amount", "min_balance", "min_balance_date", "signal", "first_below_safe_date"]
    summary.writerow(["case_id", *cols])
    for c in CASES:
        cases.writerow([c["id"], c["title"], c["base"], c["start"], c["safe"], c.get("note", "")])
        for i, (day, amount, label) in enumerate(events_of(c), 1):
            events.writerow([c["id"], f"{c['id']}-E{i:02d}", day, "IN" if amount > 0 else "OUT", abs(amount), label])
        daily, s = compute(c)
        for i, (dt, b) in enumerate(daily, 1):
            daily_out.writerow([c["id"], i, dt.isoformat(), b])
        summary.writerow([c["id"], *(s[k] for k in cols)])


if __name__ == "__main__":
    main()
