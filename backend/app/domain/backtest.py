"""예측 정확도 백테스트 (US-16 T8·T9). 과거 거래내역(거래 후 잔액 포함)만으로 돌리는 순수 함수다.

기준일 d를 일주일씩 옮기며:
1. d 전 거래만 보고 정기 일정을 찾는다 (transactions.detect, 화면의 CSV 불러오기와 같은 규칙)
2. d 전날 실제 잔액에서 시작해 28일(4주) 예상 잔액을 계산한다 (cashflow_engine, 실제 서비스와 같은 엔진)
3. 그 28일의 실제 하루 끝 잔액과 비교한다
지표 (T9):
- 경보일: 잔액이 처음 안전 잔액 미만(또는 0원 미만)이 되는 날. 예측·실제 경보일 차이(일)
- 적중: 예측과 실제 모두 경보, 오경보: 예측만 경보, 놓침: 실제만 경보, 정상: 둘 다 없음
- 잔액 오차: 날짜별 |예측 - 실제| 평균 (MAE)
반복되지 않는 거래(카드 매출 등)는 일정으로 등록되지 않으므로 예측에 빠진다. 그 차이가 그대로 오차로 나온다.
irregular=True면 기준일 전 28일 동안 정기 일정 밖 입출금의 하루 평균을 매일 더해 본다 (비교용, 서비스 예측에는 아직 없음).

비교 방법 (method):
- schedule: 정기 일정만 (서비스와 같은 방식)
- schedule+irregular: 정기 일정 + 비정기 입출금 하루 평균
- flat (기준선): 잔액이 그대로라고 가정
- trend (기준선): 지난 28일 하루 평균 순입출금만큼 매일 움직인다고 가정
안전 잔액을 주지 않으면(None) 기준일 전 잔액의 하위 20% 값을 그 계좌의 "평소보다 낮은 잔액" 기준으로 쓴다.
"""
from dataclasses import dataclass
from datetime import date, timedelta

from . import cashflow_engine
from .constants import ALERT_DAYS
from .enums import PayCycle
from .schedule import due_dates, parse_months
from .transactions import Txn, _name_key, detect

STEP_DAYS = 7
METHODS = ("schedule", "schedule+irregular", "flat", "trend")
HISTORY_DAYS = 180  # 일정 찾기에 쓰는 기준일 전 기간 (아주 긴 계좌에서 계산량을 줄인다)
MIN_HISTORY_DAYS = 56  # 매월 일정을 2번 이상 봐야 찾을 수 있다


@dataclass
class Point:
    base_date: date
    schedules: int
    predicted_alert: date | None
    actual_alert: date | None
    outcome: str  # HIT / FALSE_ALARM / MISS / OK
    alert_error_days: int | None
    mae: int
    start_below: bool = False  # 기준일 전날 이미 기준 아래였다 (예측할 것이 없는 경우)


def actual_daily(txns: list[Txn]) -> dict[date, int]:
    """하루 마지막 거래 후 잔액. 거래 없는 날은 전날 잔액을 이어 쓴다."""
    end: dict[date, int] = {}
    for t in txns:  # 같은 날은 일어난 순서대로 정렬되어 있다 (parse_csv)
        if t.balance is not None:
            end[t.day] = t.balance
    if not end:
        return {}
    days = sorted(end)
    out, d, bal = {}, days[0], end[days[0]]
    while d <= days[-1]:
        bal = end.get(d, bal)
        out[d] = bal
        d += timedelta(days=1)
    return out


def _alert(daily: list[tuple[date, int]], safe: int) -> date | None:
    return next((d for d, b in daily if b < safe), None)


def _events(hist: list[Txn], d: date, method: str) -> tuple[list[tuple[date, int]], int]:
    """(예상 입출금 목록, 찾은 정기 일정 수)"""
    if method == "flat":
        return [], 0
    recent = [t for t in hist if t.day >= d - timedelta(days=ALERT_DAYS)]
    if method == "trend":
        per_day = round(sum(t.amount for t in recent) / ALERT_DAYS)
        return [(d + timedelta(days=i), per_day) for i in range(ALERT_DAYS)], 0
    cands = detect(hist)
    events = []
    for c in cands:
        for due in due_dates(PayCycle(c.pay_cycle), c.pay_day, d, parse_months(c.months)):
            events.append((due, c.amount if c.direction == "IN" else -c.amount))
    if method == "schedule+irregular":
        known = {(c.name, c.direction) for c in cands}
        rest = [t for t in recent if (_name_key(t.desc), "IN" if t.amount > 0 else "OUT") not in known]
        per_day = round(sum(t.amount for t in rest) / ALERT_DAYS)
        events += [(d + timedelta(days=i), per_day) for i in range(ALERT_DAYS)]
    return events, len(cands)


def run(txns: list[Txn], safe_balance: int | None, step: int = STEP_DAYS, irregular: bool = False, method: str | None = None) -> list[Point]:
    method = method or ("schedule+irregular" if irregular else "schedule")
    actual = actual_daily(txns)
    if not actual:
        return []
    first, last = min(actual), max(actual)
    d = first + timedelta(days=MIN_HISTORY_DAYS)
    out: list[Point] = []
    while d + timedelta(days=ALERT_DAYS - 1) <= last:
        hist = [t for t in txns if d - timedelta(days=HISTORY_DAYS) <= t.day < d]
        events, n = _events(hist, d, method)
        if safe_balance is None:
            past = sorted(b for x, b in actual.items() if d - timedelta(days=HISTORY_DAYS) <= x < d)
            safe = past[len(past) // 5]
        else:
            safe = safe_balance
        start = actual[d - timedelta(days=1)]
        f = cashflow_engine.forecast(d, start, safe, events)
        pred = f.daily[:ALERT_DAYS]
        act = [(x, actual[x]) for x, _ in pred]
        pa, aa = _alert(pred, safe), _alert(act, safe)
        outcome = "HIT" if pa and aa else "FALSE_ALARM" if pa else "MISS" if aa else "OK"
        out.append(Point(base_date=d, schedules=n, predicted_alert=pa, actual_alert=aa, outcome=outcome,
                         alert_error_days=(pa - aa).days if pa and aa else None,
                         mae=round(sum(abs(p - a) for (_, p), (_, a) in zip(pred, act)) / len(pred)), start_below=start < safe))
        d += timedelta(days=step)
    return out


def summary(points: list[Point]) -> dict:
    n = len(points)
    cnt = {k: sum(p.outcome == k for p in points) for k in ("HIT", "FALSE_ALARM", "MISS", "OK")}
    errs = [abs(p.alert_error_days) for p in points if p.alert_error_days is not None]
    alerts = cnt["HIT"] + cnt["FALSE_ALARM"]
    # 적중률 = 실제 경보 중 미리 잡은 비율(재현율), 오경보 비율 = 낸 경보 중 실제로 없던 비율 (1 - 정밀도)
    return {
        "runs": n, **{k.lower(): v for k, v in cnt.items()},
        "hit_rate": round(cnt["HIT"] / (cnt["HIT"] + cnt["MISS"]), 3) if cnt["HIT"] + cnt["MISS"] else None,  # 실제 경보 중 미리 잡은 비율
        "false_alarm_rate": round(cnt["FALSE_ALARM"] / alerts, 3) if alerts else None,  # 낸 경보 중 틀린 비율
        "alert_error_days_mean": round(sum(errs) / len(errs), 1) if errs else None,
        "mae_mean": round(sum(p.mae for p in points) / n) if n else None,
    }
