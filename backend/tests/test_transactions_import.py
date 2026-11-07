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


HEADER = "거래일자,내용,출금액,입금액,거래후잔액\n"
SAME_DAY = ["2026-10-31,첫거래,100000,,900000\n", "2026-10-31,중간,,50000,950000\n", "2026-10-31,마지막,200000,,750000\n"]
TWO_DAYS = ["2026-10-30,전날,100000,,900000\n", *SAME_DAY[1:]]


@pytest.mark.parametrize("rows, balance", [(SAME_DAY, 750_000), (TWO_DAYS, 750_000)])
def test_last_balance_same_in_either_file_order(rows, balance):
    """최신 거래가 위에 있는 은행 파일에서도 그날 마지막 거래의 잔액을 쓴다."""
    for ordered in (rows, rows[::-1]):
        assert tx.last_balance(tx.parse_csv(HEADER + "".join(ordered))) == (date(2026, 10, 31), balance)


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


def test_same_schedule_finds_other_name():
    c = tx.Candidate(name="국민은행 대출원리금", direction="OUT", kind="LOAN", pay_cycle="MONTHLY", pay_day=15, amount=2_400_000, count=3)
    loan = tx.Registered("운영자금대출", "OUT", "MONTHLY", 15, 2_400_000)
    assert tx.same_schedule(c, [loan]) == "운영자금대출"
    assert tx.same_schedule(c, [tx.Registered("다른날", "OUT", "MONTHLY", 16, 2_400_000)]) is None
    assert tx.same_schedule(c, [tx.Registered("다른금액", "OUT", "MONTHLY", 15, 3_000_000)]) is None
    assert tx.same_schedule(c, [tx.Registered("받는돈", "IN", "MONTHLY", 15, 2_400_000)]) is None


def test_import_api_same_loan_other_name(client):
    client.post("/api/loans", json={"name": "운영자금대출", "lender": "○○은행", "principal": 60_000_000, "interest_rate": 5.1,
                                    "rate_type": "FIXED", "installment": 2_400_000, "repay_day": 15}).raise_for_status()
    body = client.post("/api/imports/transactions", json={"text": SAMPLE.read_text(encoding="utf-8-sig")}).json()
    loan = next(c for c in body["candidates"] if c["name"] == "국민은행 대출원리금")
    assert loan["already"] is True and loan["same_as"] == "운영자금대출"


def test_import_api_broken_file_is_not_server_error(client):
    r = client.post("/api/imports/transactions", json={"text": '"' + "a" * 200_000})
    assert r.status_code == 422 and "CSV" in r.json()["detail"]


def test_import_api_bad_file(client):
    r = client.post("/api/imports/transactions", json={"text": "hello"})
    assert r.status_code == 422 and "거래일" in r.json()["detail"]
