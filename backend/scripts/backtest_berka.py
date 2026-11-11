"""US-16 확장: 공개 실제 은행 거래 데이터(PKDD'99 Berka, 체코 은행 익명 계좌)로 28일 예측을 기준선과 비교한다.

데이터는 레포에 넣지 않는다 (배포 조건이 명시되어 있지 않아 받은 사람 PC에서만 쓴다).
받는 곳: CTU Relational Dataset Repository "Financial" (https://relational.fel.cvut.cz/dataset/Financial) 또는 PKDD'99 Discovery Challenge 원본의 trans.asc.
실행 (backend 폴더): .venv/bin/python -m scripts.backtest_berka <trans.asc 경로> [--accounts 300] [--step 28]

- 개인 계좌라 가게 계좌와 다르다. 다만 정기 입금(급여·연금)·정기 출금(자동이체·대출 상환)·비정기 출금(현금 인출)이 섞인 구조는 같다.
- 안전 잔액은 계좌마다 다르므로, 기준일 전 잔액의 하위 20%를 "평소보다 낮은 잔액" 기준으로 쓴다 (backtest.run safe_balance=None).
- 잔액 오차는 계좌 규모가 달라 기준일 잔액 대비 비율(%)로도 본다.
"""
import argparse
import csv
import statistics
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

from app.domain import backtest as bt
from app.domain.transactions import Txn


def _letters(n: str) -> str:
    """상대 계좌번호를 글자로 바꾼다: 일정 찾기가 4자리 이상 숫자를 이름에서 지우기 때문 (transactions._name_key)."""
    v, out = int(n or 0), ""
    while v:
        v, r = divmod(v, 26)
        out += "ABCDEFGHIJKLMNOPQRSTUVWXYZ"[r]
    return out


def load(path: Path) -> dict[int, list[Txn]]:
    rows = defaultdict(list)
    with path.open(encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter=";"):
            ymd = r["date"]
            day = date(1900 + int(ymd[:2]), int(ymd[2:4]), int(ymd[4:6]))
            amt = round(float(r["amount"]))
            amt = amt if r["type"] == "PRIJEM" else -amt
            k = r["k_symbol"].strip()
            desc = " ".join(x for x in (k or r["operation"].strip() or r["type"], _letters(r["account"])) if x)
            rows[int(r["account_id"])].append((day, int(r["trans_id"]), Txn(day=day, desc=desc, amount=amt, balance=round(float(r["balance"])))))
    return {a: [t for _, _, t in sorted(v, key=lambda x: (x[0], x[1]))] for a, v in rows.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("trans", type=Path)
    ap.add_argument("--accounts", type=int, default=300, help="계좌 번호 순으로 앞에서부터 쓸 계좌 수 (1년 이상 거래가 있는 계좌만)")
    ap.add_argument("--step", type=int, default=28)
    a = ap.parse_args()
    data = load(a.trans)
    ids = [i for i in sorted(data) if (data[i][-1].day - data[i][0].day).days >= 365][: a.accounts]
    res = {m: [] for m in bt.METHODS}
    rel = {m: [] for m in bt.METHODS}
    for i in ids:
        txns = data[i]
        for m in bt.METHODS:
            # 기준일에 이미 기준 아래인 계좌는 뺀다: "잔액 유지"도 첫날 경보를 내서 맞히는 셈이 되어 비교가 불공평하다
            pts = [p for p in bt.run(txns, None, a.step, method=m) if not p.start_below]
            res[m] += pts
            bal = bt.actual_daily(txns)
            rel[m] += [p.mae / max(1, abs(bal[p.base_date - timedelta(days=1)])) for p in pts]
    n = len(res["flat"])
    print(f"데이터: PKDD'99 Berka 실제 익명 계좌 {len(ids)}개 · 기준일 {n}개 (계좌마다 {a.step}일 간격, 기준일에 이미 낮은 잔액인 경우 제외) · 28일 예측\n")
    print("| 방법 | 경보 적중률 | 오경보 비율 | 경보일 평균 오차 | 잔액 오차 중앙값 (기준일 잔액 대비) | 실제 경보 / 낸 경보 |")
    print("| --- | --- | --- | --- | --- | --- |")
    name = {"schedule": "정기 일정 (서비스 방식)", "schedule+irregular": "정기 일정 + 비정기 평균", "flat": "기준선: 잔액 유지", "trend": "기준선: 지난 4주 추세"}
    pct = lambda v: f"{v * 100:.0f}%" if v is not None else "-"  # noqa: E731
    for m in bt.METHODS:
        s = bt.summary(res[m])
        print(f"| {name[m]} | {pct(s['hit_rate'])} | {pct(s['false_alarm_rate'])} | {s['alert_error_days_mean'] if s['alert_error_days_mean'] is not None else '-'}일 | "
              f"{statistics.median(rel[m]) * 100:.1f}% | {s['hit'] + s['miss']} / {s['hit'] + s['false_alarm']} |")


if __name__ == "__main__":
    main()
