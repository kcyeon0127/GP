"""입력 편의: 거래내역 CSV 읽기·반복 거래 찾기 (domain) 와 후보 API."""
from datetime import date
from pathlib import Path

import pytest

from app.domain import transactions as tx

SAMPLE = Path(__file__).resolve().parents[1] / "data" / "sample_bank_transactions.csv"


def test_parse_skips_preamble_and_reads_in_out_columns():
    txns = tx.parse_csv(SAMPLE.read_text(encoding="utf-8-sig"))
    assert len(txns) == 116
    assert txns[0].day == date(2026, 8, 1)
    assert tx.last_balance(txns) == (date(2026, 10, 31), 3_478_600)


def test_parse_signed_amount_column():
    text = "거래일자,내용,금액,잔액\n2026-10-06,임대료,-1500000,100\n2026-11-06,임대료,\"-1,500,000\",50\n"
    txns = tx.parse_csv(text)
    assert [t.amount for t in txns] == [-1_500_000, -1_500_000]


def test_parse_rejects_unknown_format():
    with pytest.raises(tx.CsvFormatError):
        tx.parse_csv("a,b,c\n1,2,3\n")


def test_detect_sample():
    found = {c.name: c for c in tx.detect(tx.parse_csv(SAMPLE.read_text(encoding="utf-8-sig")))}
    assert set(found) == {"한빛식자재", "새봄마트", "국민은행 대출원리금", "대성유통", "임대료", "우리농산", "서울도시가스", "KT 통신요금"}
    assert (found["한빛식자재"].kind, found["한빛식자재"].pay_cycle, found["한빛식자재"].pay_day) == ("SALES", "MONTHLY", 7)
    assert found["새봄마트"].pay_day == 15  # 8/17(공휴일 밀림)이 있어도 15일
    assert found["임대료"].kind == "FIXED_COST"  # '임대료(8월분)' 처럼 달이 붙어도 하나로 묶는다
    assert found["국민은행 대출원리금"].kind == "LOAN"
    assert (found["우리농산"].pay_cycle, found["우리농산"].pay_day, found["우리농산"].kind) == ("WEEKLY", 1, "PURCHASE")
    assert found["서울도시가스"].pay_day == 31 and found["서울도시가스"].varies  # 매달 말일, 금액은 중앙값
    assert "카드매출 입금" not in found  # 매일 금액이 들쭉날쭉한 입금은 정기 일정이 아니다


def test_detect_quarterly_fixed_cost():
    text = "거래일자,내용,금액\n2026-01-25,부가세 납부,-900000\n2026-04-25,부가세 납부,-1000000\n2026-07-27,부가세 납부,-950000\n"
    [c] = tx.detect(tx.parse_csv(text))
    assert (c.kind, c.pay_cycle, c.pay_day, c.months) == ("FIXED_COST", "QUARTERLY", 25, "1,4,7,10")


def test_import_api_marks_registered(client):
    client.post("/api/counterparties", json={"name": "한빛식자재", "trade_type": "SALES", "pay_cycle": "MONTHLY", "pay_day": 7, "amount": 3_200_000})
    r = client.post("/api/imports/transactions", json={"text": SAMPLE.read_text(encoding="utf-8-sig")})
    assert r.status_code == 200
    body = r.json()
    assert body["rows"] == 116 and body["last_balance"] == {"date": "2026-10-31", "balance": 3_478_600}
    already = {c["name"]: c["already"] for c in body["candidates"]}
    assert already["한빛식자재"] is True and already["새봄마트"] is False


def test_import_api_bad_file(client):
    r = client.post("/api/imports/transactions", json={"text": "hello"})
    assert r.status_code == 422 and "거래일" in r.json()["detail"]
