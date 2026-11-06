"""시연용 사업장(한결 식자재 납품) 데이터를 API로 등록하고, 계약 문서를 임베딩해 넣고(T24), 그래프를 동기화한다.

실행 (backend 폴더): .venv/bin/python -m scripts.seed_demo [--base-date YYYY-MM-DD]
필요: docker compose up -d, 임베딩 서버 SSH 터널 (ssh -N -L 8101:127.0.0.1:8101 lab)
기존 사업장 데이터는 지우고 다시 만든다.

시연 목표 상태 (docs/demo.md): 시드 직후 홈은 노랑, 한빛식자재 결제일을 7일→21일로 고치면 빨강.
월 고정 일정이라 기준일에 따라 4주 구간의 입출금이 달라지므로, 시작 잔액은 기준일에 맞춰 계산한다 (opening_balance).
"""
import argparse
import json
from datetime import date
from pathlib import Path

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.db import SessionLocal, init_db
from app.domain import cashflow_engine
from app.domain.constants import ALERT_DAYS
from app.domain.enums import PayCycle
from app.domain.schedule import due_dates, parse_months
from app.main import app
from app.models import CashEvent, Contract, Counterparty, Document, DocumentChunk, FixedCost, Loan
from app.repositories import embedding_client
from app.repositories.business import get_or_create

DATA = Path(__file__).resolve().parent.parent / "data"

SAFETY_BALANCE = 2_000_000
YELLOW_MARGIN = 300_000  # 시드 직후 4주 최저 잔액을 안전 잔액보다 이만큼 아래에 둔다
DEMO_PARTY = "한빛식자재"
DEMO_DAY_BEFORE, DEMO_DAY_AFTER = 7, 21  # 시연에서 고치는 결제일 (정산 14일 지연)

# 월 매출 약 2,790만 원, 지출 약 2,680만 원인 소규모 식자재 납품업 규모
COUNTERPARTIES = [
    dict(name=DEMO_PARTY, trade_type="SALES", pay_cycle="MONTHLY", pay_day=DEMO_DAY_BEFORE, amount=9_800_000),
    dict(name="청춘마켓", trade_type="SALES", pay_cycle="MONTHLY", pay_day=13, amount=6_400_000),
    dict(name="온누리푸드", trade_type="SALES", pay_cycle="MONTHLY", pay_day=21, amount=8_600_000),
    dict(name="A카드", trade_type="SALES", pay_cycle="WEEKLY", pay_day=1, amount=720_000),  # 표준약관은 2영업일 지급이 원칙이나, 입금을 주 단위로 묶어 잡는다 (월요일)
    dict(name="대성유통", trade_type="PURCHASE", pay_cycle="MONTHLY", pay_day=9, amount=14_200_000),
]
FIXED_COSTS = [
    dict(name="임대료", pay_cycle="MONTHLY", pay_day=6, amount=1_650_000, payee="건물주"),
    dict(name="4대보험", pay_cycle="MONTHLY", pay_day=10, amount=540_000, payee="국민건강보험공단"),
    dict(name="인건비", pay_cycle="MONTHLY", pay_day=11, amount=4_600_000, payee="직원"),
    dict(name="카드대금", pay_cycle="MONTHLY", pay_day=14, amount=1_350_000, payee="B카드"),
    dict(name="공과금", pay_cycle="MONTHLY", pay_day=15, amount=480_000),
    dict(name="화재보험료", pay_cycle="QUARTERLY", pay_day=31, amount=280_000, payee="○○화재"),
    # 부가세 예정고지·확정신고는 1·4·7·10월 25일에 낸다
    dict(name="부가세", pay_cycle="QUARTERLY", pay_day=25, months="1,4,7,10", amount=1_900_000, payee="세무서"),
]
LOANS = [
    dict(name="운영자금대출", lender="○○은행", principal=62_000_000, interest_rate=5.1, rate_type="VARIABLE", installment=2_400_000, repay_day=15),
    dict(name="시설자금대출", lender="△△은행", principal=18_000_000, interest_rate=3.8, rate_type="FIXED", installment=900_000, repay_day=25),
]
# 계약 문서 → 연결할 거래처(계약 상대) 이름.
DOC_PARTY = {"D01": DEMO_PARTY, "D02": "청춘마켓", "D03": "온누리푸드", "D04": "대성유통", "D05": "건물주",
             "D06": "○○은행", "D07": "△△은행", "D08": "직원", "D09": "A카드", "D10": "○○화재"}


def scheduled_events(base: date, demo_day: int = DEMO_DAY_BEFORE) -> list[tuple[date, int]]:
    """시드 일정이 만드는 (날짜, 금액) 목록. demo_day로 한빛식자재 결제일을 바꿔 볼 수 있다."""
    out: list[tuple[date, int]] = []
    for c in COUNTERPARTIES:
        day = demo_day if c["name"] == DEMO_PARTY else c["pay_day"]
        sign = 1 if c["trade_type"] == "SALES" else -1
        out += [(d, sign * c["amount"]) for d in due_dates(PayCycle(c["pay_cycle"]), day, base)]
    for f in FIXED_COSTS:
        out += [(d, -f["amount"]) for d in due_dates(PayCycle(f["pay_cycle"]), f["pay_day"], base, months=parse_months(f.get("months")))]
    for l in LOANS:
        out += [(d, -l["installment"]) for d in due_dates(PayCycle.MONTHLY, l["repay_day"], base)]
    return out


def opening_balance(base: date) -> int:
    """4주 최저 잔액이 안전 잔액 - YELLOW_MARGIN이 되는 시작 잔액 (1만 원 단위 내림)."""
    daily = cashflow_engine.forecast(base, 0, SAFETY_BALANCE, scheduled_events(base)).daily
    lowest = min(b for _, b in daily[:ALERT_DAYS])
    return (SAFETY_BALANCE - YELLOW_MARGIN - lowest) // 10_000 * 10_000


def is_delay(base: date) -> bool:
    """이 기준일에서 결제일 7일→21일 수정이 실제 지연인지.

    8~21일이 기준일이면 다음 예정일이 '다음 달 7일'에서 '이번 달 21일'로 오히려 앞당겨져 빨강이 되지 않는다.
    """
    return not (DEMO_DAY_BEFORE < base.day <= DEMO_DAY_AFTER)


def resolve_base_date(requested: date | None, today: date | None = None) -> date:
    """옵션이 있으면 그 날을, 없으면 오늘을 쓴다. 오늘이 8~21일이면 시연 전환이 되도록 이번 달 7일로 당긴다."""
    if requested:
        if not is_delay(requested):
            print(f"경고: 기준일 {requested}에서는 한빛식자재 결제일을 21일로 고쳐도 빨강이 되지 않습니다. 22일~다음 달 7일 사이를 쓰세요.")
        return requested
    today = today or date.today()
    if is_delay(today):
        return today
    base = today.replace(day=DEMO_DAY_BEFORE)
    print(f"안내: 오늘({today})은 결제일 수정이 지연이 되지 않는 날짜라 기준일을 {base}로 둡니다. 화면의 기준일도 {base}로 보입니다.")
    return base


def reset(s, bid):
    for model in (CashEvent, Document, FixedCost, Loan, Counterparty):
        s.execute(delete(model).where(model.business_id == bid))
    s.commit()


def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description="시연 데이터 시드")
    parser.add_argument("--base-date", type=date.fromisoformat, help="기준일 YYYY-MM-DD (기본: 오늘)")
    base = resolve_base_date(parser.parse_args(argv).base_date)
    docs = json.loads((DATA / "contracts.json").read_text())
    # 임베딩을 먼저 받는다: 터널이 끊겨 있을 때 기존 시연 데이터를 지운 채로 멈추지 않게 한다.
    try:
        vectors = embedding_client.embed([f"{d['title']} {text}" for d in docs for text in d["chunks"]])
    except httpx.HTTPError as e:
        raise SystemExit(f"임베딩 서버에 닿지 않아 시드를 멈췄습니다. 기존 데이터는 그대로입니다. SSH 터널과 EMBEDDING_API_KEY를 확인하세요: {e}")
    init_db()
    with SessionLocal() as s:
        b = get_or_create(s)
        b.name = "한결 식자재 납품"
        s.commit()
        reset(s, b.business_id)
    c = TestClient(app)
    c.post("/api/forecasts", json={"base_date": base.isoformat(), "current_balance": opening_balance(base), "safety_balance": SAFETY_BALANCE}).raise_for_status()
    for body in COUNTERPARTIES:
        c.post("/api/counterparties", json=body).raise_for_status()
    for body in FIXED_COSTS:
        c.post("/api/fixed-costs", json=body).raise_for_status()
    for body in LOANS:
        c.post("/api/loans", json=body).raise_for_status()

    with SessionLocal() as s:
        b = get_or_create(s)
        rows = []
        for d in docs:
            party = DOC_PARTY[d["doc"]]
            cid = s.scalar(select(Contract.contract_id).join(Counterparty).where(Counterparty.business_id == b.business_id, Counterparty.name == party)) if party else None
            doc = Document(business_id=b.business_id, contract_id=cid, key=d["doc"], title=d["title"])
            s.add(doc)
            s.flush()
            for i, text in enumerate(d["chunks"], 1):
                rows.append(DocumentChunk(document_id=doc.document_id, contract_id=cid, key=f"{d['doc']}-{i}", text=text, embedding=None))
        for row, vec in zip(rows, vectors):
            row.embedding = vec
        s.add_all(rows)
        s.commit()
        print(f"문서 {len(docs)}건, 조각 {len(rows)}개 임베딩 적재")
    print("그래프:", json.dumps(c.post("/api/graph/sync").json(), ensure_ascii=False))
    r = c.post("/api/forecasts", json={}).json()
    print(f"기준일 {r['base_date']} · 시작 잔액 {r['start_balance']:,}원 · 안전 잔액 {r['safety_balance']:,}원")
    print(f"예상 잔액: {r['signal']} · 안전 잔액 미만 {r['first_below_safe_date']} · 최저 {r['min_balance']:,}원 ({r['min_balance_date']})")
    if r["signal"] != "YELLOW":
        raise SystemExit(f"시드 직후 신호가 노랑이 아닙니다: {r['signal']}")


if __name__ == "__main__":
    main()
