"""US-17 거래내역 입력 예외 처리: 오류 행 안내(T11), 거래처명 병합 제안(T12), 예외 사례(T14)."""
from datetime import date

import pytest

from app.domain import transactions as tx

HEADER = "거래일자,내용,출금액,입금액,거래후잔액\n"


def _check(*rows: str):
    return tx.parse_checked(HEADER + "".join(rows))


@pytest.mark.parametrize("row, reason", [
    ("2026-10-02,임대료,1500000\n", "칸 수"),
    ("10월 2일,임대료,1500000,,100\n", "날짜"),
    ("2026-13-40,임대료,1500000,,100\n", "날짜"),
    ("2026-10-02,임대료,천오백,,100\n", "숫자"),
    ("2026-10-02,임대료,,,100\n", "비어"),
    ("2026-10-02,,1500000,,100\n", "내용"),
    ("2026-10-02,이상한줄,1000,2000,100\n", "같이"),
])
def test_bad_row_is_reported_and_skipped(row, reason):
    txns, issues = _check("2026-10-01,정상,,500000,600000\n", row)
    assert [t.desc for t in txns] == ["정상"]  # 정상 행만 반영
    assert len(issues) == 1 and issues[0].line == 3 and reason in issues[0].reason


def test_duplicate_row():
    row = "2026-10-01 09:00,한빛식자재,,3000000,3100000\n"
    txns, issues = _check(row, row)
    assert len(txns) == 1 and issues[0].line == 3 and "중복" in issues[0].reason and "2번째" in issues[0].reason


def test_same_amount_twice_with_different_balance_is_not_duplicate():
    txns, issues = _check("2026-10-01,우리농산,500000,,1000000\n", "2026-10-01,우리농산,500000,,500000\n")
    assert len(txns) == 2 and issues == []


def test_footer_and_blank_lines_are_not_errors():
    txns, issues = _check("2026-10-01,정상,,500000,600000\n", "\n", ",,,,\n", "합계,,1000,500000,\n", "총 1건\n")
    assert len(txns) == 1 and issues == []


def test_all_rows_bad_is_format_error():
    with pytest.raises(tx.CsvFormatError):
        _check("날짜없음,임대료,1500000,,100\n")


def test_canonical_name():
    assert tx.canonical("(주)한빛 식자재") == tx.canonical("한빛식자재㈜") == tx.canonical("주식회사 한빛식자재") == "한빛식자재"
    assert tx.canonical("KT 통신요금") == tx.canonical("kt통신요금")


def _months(name_by_month):
    rows = [f"2026-{m:02d}-07,{n},,3000000,{m}000000\n" for m, n in name_by_month]
    return tx.parse_csv(HEADER + "".join(rows))


def test_merge_suggestion_and_detect_with_merge():
    txns = _months([(8, "(주)한빛식자재"), (9, "한빛식자재"), (10, "한빛 식자재")])
    assert tx.detect(txns) == []  # 표기가 달라 한 번씩만 보여 반복으로 못 찾는다
    [m] = tx.merge_suggestions(txns)
    assert set(m.names) == {"(주)한빛식자재", "한빛식자재", "한빛 식자재"} and m.count == 3
    [c] = tx.detect(txns, {n: "한빛식자재" for n in m.names})
    assert (c.name, c.count, c.pay_day) == ("한빛식자재", 3, 7)


def test_merge_to_registered_name():
    txns = _months([(8, "한빛식자재㈜"), (9, "한빛식자재㈜")])
    [m] = tx.merge_suggestions(txns, ["한빛식자재"])
    assert m.to == "한빛식자재"
    c = tx.Candidate(name="한빛식자재㈜", direction="IN", kind="SALES", pay_cycle="MONTHLY", pay_day=7, amount=3_000_000, count=2)
    assert tx.same_schedule(c, [tx.Registered("한빛식자재", "IN", "MONTHLY", 1, 1)]) == "한빛식자재"


def test_sample_file_has_no_issues():
    from pathlib import Path
    text = (Path(__file__).resolve().parents[1] / "data" / "sample_bank_transactions.csv").read_text(encoding="utf-8-sig")
    txns, issues = tx.parse_checked(text)
    assert len(txns) == 116 and issues == [] and tx.merge_suggestions(txns) == []


def test_import_api_returns_issues_and_merges(client):
    text = HEADER + "2026-08-07,(주)새봄상회,,3000000,1\n2026-09-07,새봄상회,,3000000,2\n2026-10-07,새봄 상회,,3000000,3\n2026-10-08,새봄상회,abc,,4\n"
    body = client.post("/api/imports/transactions", json={"text": text}).json()
    assert body["rows"] == 3 and [(x["line"], "숫자" in x["reason"]) for x in body["issues"]] == [(5, True)]
    assert body["candidates"] == [] and len(body["merge_suggestions"]) == 1
    names = body["merge_suggestions"][0]["names"]
    again = client.post("/api/imports/transactions", json={"text": text, "merges": {n: "새봄상회" for n in names}}).json()
    assert [c["name"] for c in again["candidates"]] == ["새봄상회"] and again["merge_suggestions"] == []
