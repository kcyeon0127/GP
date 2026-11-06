"""시연 데이터 (docs/demo.md): 어느 날 시드해도 노랑 → 결제일 수정 → 빨강이 되고, 계약 문서·평가 질문이 서로 맞는다."""
import json
from datetime import date, timedelta
from pathlib import Path

from app.domain.cashflow_engine import forecast
from app.domain.enums import SignalLevel
from scripts import seed_demo as sd

DATA = Path(sd.__file__).resolve().parent.parent / "data"
TWO_YEARS = [date(2026, 1, 1) + timedelta(days=i) for i in range(731)]


def states(base: date):
    balance = sd.opening_balance(base)
    return (forecast(base, balance, sd.SAFETY_BALANCE, sd.scheduled_events(base)),
            forecast(base, balance, sd.SAFETY_BALANCE, sd.scheduled_events(base, sd.DEMO_DAY_AFTER)))


def test_yellow_then_red_on_any_day():
    for today in TWO_YEARS:
        before, after = states(sd.resolve_base_date(None, today))
        assert before.signal == SignalLevel.YELLOW, today
        assert before.first_shortage_date is None, today  # 12주 안에도 0원 아래로 내려가지 않는다
        assert after.signal == SignalLevel.RED and after.shortage_amount > 0, today


def test_base_date_defaults_to_today_when_edit_is_a_real_delay():
    assert sd.resolve_base_date(None, date(2026, 11, 7)) == date(2026, 11, 7)
    assert sd.resolve_base_date(None, date(2026, 11, 25)) == date(2026, 11, 25)
    assert sd.resolve_base_date(None, date(2026, 11, 15)) == date(2026, 11, 7)  # 8~21일은 이번 달 7일로 당긴다
    assert sd.resolve_base_date(date(2026, 11, 15), date(2026, 11, 25)) == date(2026, 11, 15)  # 옵션은 그대로 따른다


def test_contracts_keep_keys_and_shape():
    docs = json.loads((DATA / "contracts.json").read_text())
    assert [d["doc"] for d in docs] == [f"D{i:02d}" for i in range(1, 11)]
    assert set(sd.DOC_PARTY) == {d["doc"] for d in docs}
    for d in docs:
        assert d["title"] and 2 <= len(d["chunks"]) <= 4
        assert d["source"].startswith("https://") and d["revision"]  # 공개 원문의 출처·개정일


def test_eval_questions_point_at_existing_chunks():
    docs = json.loads((DATA / "contracts.json").read_text())
    keys = {f"{d['doc']}-{i}" for d in docs for i in range(1, len(d["chunks"]) + 1)}
    questions = json.loads((DATA / "eval_questions.json").read_text())
    assert len(questions) == 20
    assert sum(not q["required"] for q in questions) == 1  # 근거 없음 정답 질문
    for q in questions:
        assert set(q["required"]) <= keys, q["id"]
