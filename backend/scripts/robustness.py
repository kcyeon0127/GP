"""US-16 강건성 테스트: 직접 만든 가게 데이터로 "지연·잡음이 커질 때 경보가 얼마나 버티는가"를 본다.

정확도 근거가 아니다 (규칙을 알고 만든 데이터). 정확도는 scripts.backtest_berka로 말한다.
실행 (backend 폴더): .venv/bin/python -m scripts.robustness [--stores 50] [--seed 1]

비교 (모두 대표자가 결제조건을 등록했다고 가정):
- 등록 조건만: 약속 결제일 그대로 (지금 홈 경보와 같은 방식)
- 등록 + 지연 반영: 기준일 전 거래로 거래처별 평균 지연일을 추정(US-14)해 입금을 민다 (US-15 보수 예측)
- 기준선 4주 추세: 지난 28일 하루 평균 순입출금
경보 = 28일 안에 잔액이 그 가게의 기준일 전 하위 20% 아래로 내려감. 기준일에 이미 아래인 경우는 뺀다.
"""
import argparse
from datetime import date, timedelta

from app.domain import backtest as bt
from app.domain import cashflow_engine
from app.domain import payment_terms as pt
from app.domain.constants import ALERT_DAYS
from app.domain.enums import PayCycle
from app.domain.schedule import due_dates
from app.domain.synth import make_store

START = date(2025, 1, 1)
MONTHS = 12
BASES = [date(2025, 7, 1) + timedelta(days=7 * k) for k in range(22)]  # 6개월 이력 뒤 매주


def _events(st, d, delays):
    """지연을 반영하면 기준일 전에 약속됐지만 늦게 들어올 입금도 구간 안으로 들어온다 (60일 전 약속분부터 본다)."""
    out = []
    for name, cycle, day, amt in st.terms:
        lag = delays.get(name, 0) if amt > 0 else 0
        for due in due_dates(PayCycle(cycle), day, d - timedelta(days=60) if lag else d):
            when = due + timedelta(days=lag)
            if d <= when:
                out.append((when, amt))
    return out


def evaluate(stores):
    res = {"등록 조건만": [], "등록 + 지연 반영": [], "기준선: 4주 추세": []}
    for st in stores:
        actual = bt.actual_daily(st.txns)
        for d in BASES:
            if d + timedelta(days=ALERT_DAYS - 1) > max(actual):
                continue
            hist = [t for t in st.txns if t.day < d]
            past = sorted(b for x, b in actual.items() if d - timedelta(days=180) <= x < d)
            safe, start = past[len(past) // 5], actual[d - timedelta(days=1)]
            if start < safe:
                continue
            reg = [pt.Registered(i, n, "MONTHLY", day) for i, (n, day, _, _) in enumerate(st.sales)]
            est = {e.name: e.avg_delay_days for e in pt.estimate(hist, reg) if e.status == "ESTIMATED"}
            recent = [t for t in hist if t.day >= d - timedelta(days=ALERT_DAYS)]
            per_day = round(sum(t.amount for t in recent) / ALERT_DAYS)
            plans = {"등록 조건만": _events(st, d, {}), "등록 + 지연 반영": _events(st, d, est),
                     "기준선: 4주 추세": [(d + timedelta(days=i), per_day) for i in range(ALERT_DAYS)]}
            act = [(d + timedelta(days=i), actual[d + timedelta(days=i)]) for i in range(ALERT_DAYS)]
            aa = next((x for x, b in act if b < safe), None)
            for k, ev in plans.items():
                pred = cashflow_engine.forecast(d, start, safe, ev).daily[:ALERT_DAYS]
                pa = next((x for x, b in pred if b < safe), None)
                res[k].append(bt.Point(d, 0, pa, aa, "HIT" if pa and aa else "FALSE_ALARM" if pa else "MISS" if aa else "OK",
                                       (pa - aa).days if pa and aa else None, round(sum(abs(p - a) for (_, p), (_, a) in zip(pred, act)) / ALERT_DAYS)))
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stores", type=int, default=100)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    pct = lambda v: f"{v * 100:.0f}%" if v is not None else "-"  # noqa: E731
    print(f"직접 만든 가게 {a.stores}곳 × 기준일 {len(BASES)}개 (12개월 중 뒤 6개월, 매주) · 28일 예측 · seed {a.seed}")
    print("정확도 근거가 아니라 조건이 나빠질 때의 변화를 보는 표입니다.\n")
    print("| 잡음 | 평균 지연 | 방법 | 경보 적중률 | 오경보 비율 | 경보일 평균 오차 | 실제 경보 / 낸 경보 |")
    print("| --- | --- | --- | --- | --- | --- | --- |")
    for noise in (0, 1):
        for delay in (0, 3, 7, 14):
            stores = [make_store(i, START, MONTHS, delay, noise, a.seed) for i in range(a.stores)]
            for k, pts in evaluate(stores).items():
                s = bt.summary(pts)
                err = s["alert_error_days_mean"]
                print(f"| {'있음' if noise else '없음'} | {delay}일 | {k} | {pct(s['hit_rate'])} | {pct(s['false_alarm_rate'])} | "
                      f"{err if err is not None else '-'}일 | {s['hit'] + s['miss']} / {s['hit'] + s['false_alarm']} |")


if __name__ == "__main__":
    main()
