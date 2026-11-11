"""US-16 T8·T9: 과거 거래내역 CSV로 28일 예측 정확도를 잰다. DB·서버 없이 돈다.

실행 (backend 폴더): .venv/bin/python -m scripts.backtest [CSV 경로] [--safe 2000000] [--step 7] [--irregular]
CSV를 주지 않으면 data/sample_bank_transactions.csv (합성 가게 3개월)를 쓴다. 결과표는 마크다운으로 출력한다.
"""
import argparse
from pathlib import Path

from app.domain import backtest as bt
from app.domain import transactions as tx

SAMPLE = Path(__file__).resolve().parent.parent / "data" / "sample_bank_transactions.csv"
OUT_KO = {"HIT": "적중", "FALSE_ALARM": "오경보", "MISS": "놓침", "OK": "정상"}


def read(path: Path) -> str:
    raw = path.read_bytes()
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp949")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", nargs="?", type=Path, default=SAMPLE)
    ap.add_argument("--safe", type=int, default=2_000_000, help="안전 잔액 (경보 기준)")
    ap.add_argument("--step", type=int, default=bt.STEP_DAYS)
    ap.add_argument("--irregular", action="store_true", help="정기 일정 밖 입출금의 최근 28일 하루 평균을 더해 비교")
    a = ap.parse_args()
    txns, issues = tx.parse_checked(read(a.csv))
    points = bt.run(txns, a.safe, a.step, a.irregular)
    md = lambda d: f"{d.month}/{d.day}" if d else "-"  # noqa: E731
    print(f"파일: {a.csv.name} · 거래 {len(txns)}건 (읽지 못한 줄 {len(issues)}개) · 안전 잔액 {a.safe:,}원{' · 비정기 입출금 평균 포함' if a.irregular else ''}\n")
    if not points:
        print(f"기준일을 잡을 수 없어요. 거래 후 잔액이 있는 {bt.MIN_HISTORY_DAYS + 28}일 이상 거래내역이 필요해요.")
        return
    print("| 기준일 | 찾은 일정 | 예측 경보일 | 실제 경보일 | 결과 | 경보일 오차 | 잔액 오차(MAE) |")
    print("| --- | --- | --- | --- | --- | --- | --- |")
    for p in points:
        err = f"{p.alert_error_days:+d}일" if p.alert_error_days is not None else "-"
        print(f"| {md(p.base_date)} | {p.schedules} | {md(p.predicted_alert)} | {md(p.actual_alert)} | {OUT_KO[p.outcome]} | {err} | {p.mae:,}원 |")
    s = bt.summary(points)
    rate = lambda v: f"{v * 100:.0f}%" if v is not None else "-"  # noqa: E731
    print(f"\n기준일 {s['runs']}개 · 적중 {s['hit']} · 오경보 {s['false_alarm']} · 놓침 {s['miss']} · 정상 {s['ok']}")
    print(f"경보 적중률 {rate(s['hit_rate'])} · 오경보 비율 {rate(s['false_alarm_rate'])} · 경보일 평균 오차 {s['alert_error_days_mean'] or '-'}일 · 잔액 평균 오차 {s['mae_mean']:,}원")


if __name__ == "__main__":
    main()
