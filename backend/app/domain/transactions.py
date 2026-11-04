"""거래내역 파일 읽기와 반복 거래 찾기 (입력 편의). DB 없이 텍스트만 다룬다.

- parse_csv: 은행 인터넷뱅킹에서 받은 거래내역 CSV를 읽는다. 앞쪽 계좌 정보 줄은 건너뛰고,
  열 이름은 은행마다 달라서 별칭(ALIASES)으로 찾는다. 입금/출금이 나뉜 형식과 금액 한 열(부호) 형식을 모두 받는다.
- detect: 같은 상대·같은 방향으로 비슷한 날, 비슷한 금액이 반복되면 정기 일정 후보로 돌려준다.
  후보는 저장하지 않는다. 사장님이 화면에서 고른 것만 기존 등록 API로 저장한다.
"""
import csv
import io
import re
import statistics
from calendar import monthrange
from dataclasses import dataclass, field
from datetime import date

# 앞에 있는 별칭을 먼저 쓴다. desc에서 기재내용이 적요보다 앞인 이유: 적요에는 은행에 따라
# '타행이체'·'자동이체' 같은 거래 방식만 적혀 있어, 이걸로 묶으면 다른 거래처가 한 일정으로 합쳐진다.
ALIASES = {
    "date": ["거래일시", "거래일자", "거래일", "거래날짜", "일자", "날짜", "거래시간"],
    "desc": ["기재내용", "거래내용", "내용", "받는분/보낸분", "보낸분/받는분", "의뢰인/수취인", "거래처", "적요", "메모"],
    "out": ["출금액", "출금", "찾으신금액", "지급액", "출금금액"],
    "in": ["입금액", "입금", "맡기신금액", "입금금액"],
    "amount": ["거래금액", "금액"],
    "balance": ["거래후잔액", "잔액", "잔고"],
}
# 종류는 이름으로 추정할 뿐이다. 'kt'처럼 짧은 낱말은 다른 이름에 걸릴 수 있어, 화면에서 사장님이 바꿀 수 있게 했다.
LOAN_WORDS = ("대출", "원리금", "이자", "상환")
FIXED_WORDS = ("임대", "월세", "관리비", "급여", "월급", "인건비", "전기", "가스", "수도", "통신", "kt", "skt", "lg유플러스", "보험", "카드", "세금", "부가세", "납부", "국민연금", "건강보험")
MIN_COUNT = 2  # 1회는 반복인지 알 수 없다. 2회까지 받는 이유: 6개월치 파일에서 분기 일정은 2번만 나온다.
AMOUNT_TOLERANCE = 0.2  # 중앙값에서 ±20% 안이면 같은 일정으로 본다
DAY_SPREAD = 5  # 매월 일정의 날짜가 이 안에서 흔들리면 같은 일정 (주말·공휴일 밀림)


class CsvFormatError(ValueError):
    pass


@dataclass
class Txn:
    day: date
    desc: str
    amount: int  # 입금 +, 출금 -
    balance: int | None = None


@dataclass
class Candidate:
    name: str
    direction: str  # IN / OUT
    kind: str  # SALES / PURCHASE / FIXED_COST / LOAN
    pay_cycle: str  # WEEKLY / MONTHLY / QUARTERLY
    pay_day: int
    amount: int
    count: int
    dates: list[date] = field(default_factory=list)
    varies: bool = False  # 금액이 조금씩 달라 중앙값을 썼다
    months: str | None = None  # 분기 고정비 지급 월


def _norm_header(h: str) -> str:
    return re.sub(r"\s|\(원\)|\(₩\)", "", h or "").lower()


def _find(headers: list[str], key: str) -> int | None:
    for alias in ALIASES[key]:
        if alias in headers:
            return headers.index(alias)
    return None


def _money(v: str) -> int:
    v = re.sub(r"[,\s원₩]", "", v or "")
    if v in ("", "-"):
        return 0
    try:
        return int(float(v))
    except ValueError:
        return 0


def _date(v: str) -> date | None:
    m = re.search(r"(\d{4})\s*[.\-/년]?\s*(\d{1,2})\s*[.\-/월]?\s*(\d{1,2})", v or "")
    if not m:
        return None
    try:
        return date(int(m[1]), int(m[2]), int(m[3]))
    except ValueError:
        return None


def parse_csv(text: str) -> list[Txn]:
    rows = list(csv.reader(io.StringIO(text.lstrip("﻿"))))
    for i, row in enumerate(rows):
        headers = [_norm_header(c) for c in row]
        d, desc = _find(headers, "date"), _find(headers, "desc")
        out, inn, amt, bal = _find(headers, "out"), _find(headers, "in"), _find(headers, "amount"), _find(headers, "balance")
        if d is not None and desc is not None and ((out is not None and inn is not None) or amt is not None):
            break
    else:
        raise CsvFormatError("거래일·내용·입금/출금(또는 금액) 열을 찾지 못했어요. 인터넷뱅킹 거래내역 CSV인지 확인해 주세요.")
    txns: list[Txn] = []
    for row in rows[i + 1:]:
        if len(row) <= max(x for x in (d, desc, out, inn, amt, bal) if x is not None):
            continue
        day = _date(row[d])
        if day is None:
            continue
        amount = _money(row[inn]) - _money(row[out]) if out is not None and inn is not None else _money(row[amt])
        if amount == 0:
            continue
        txns.append(Txn(day=day, desc=row[desc].strip(), amount=amount, balance=_money(row[bal]) if bal is not None and row[bal].strip() else None))
    if not txns:
        raise CsvFormatError("읽을 수 있는 거래가 없어요. 날짜와 금액 칸을 확인해 주세요.")
    return sorted(txns, key=lambda t: t.day)


def _name_key(desc: str) -> str:
    """'11월 임대료', '임대료(10월분)'처럼 달마다 바뀌는 부분을 지워 같은 상대로 묶는다."""
    s = re.sub(r"\(?\d{1,2}월분?\)?", "", desc)
    s = re.sub(r"\d{4,}", "", s)
    return re.sub(r"\s+", " ", s).strip()


def _kind(name: str, direction: str, cycle: str) -> str:
    if direction == "IN":
        return "SALES"
    low = name.lower()
    if any(w in low for w in LOAN_WORDS) and cycle == "MONTHLY":
        return "LOAN"
    # 매주 나가는 돈이 매입처가 되는 이유: 고정비는 매월·분기만 등록할 수 있다 (FixedCostIn).
    if any(w in low for w in FIXED_WORDS) and cycle != "WEEKLY":
        return "FIXED_COST"
    return "PURCHASE"


def _is_month_end(d: date, slack: int = 2) -> bool:
    return monthrange(d.year, d.month)[1] - d.day <= slack


def detect(txns: list[Txn]) -> list[Candidate]:
    groups: dict[tuple[str, str], list[Txn]] = {}
    for t in txns:
        key = _name_key(t.desc)
        if key:
            groups.setdefault((key, "IN" if t.amount > 0 else "OUT"), []).append(t)
    out: list[Candidate] = []
    for (name, direction), ts in groups.items():
        if len(ts) < MIN_COUNT:
            continue
        amounts = [abs(t.amount) for t in ts]  # 평균이 아니라 중앙값: 한 번 튄 금액에 끌려가지 않게
        mid = int(statistics.median(amounts))
        if any(abs(a - mid) > mid * AMOUNT_TOLERANCE for a in amounts):
            continue  # 매일 들어오는 카드매출처럼 금액이 들쭉날쭉하면 정기 일정이 아니다
        days = [t.day for t in ts]
        gaps = [(b - a).days for a, b in zip(days, days[1:])]
        gap = statistics.median(gaps)
        # 간격도 중앙값으로 본다: 한 달을 건너뛰거나 하루 더 들어온 거래가 있어도 주기를 놓치지 않게
        if 6 <= gap <= 8 and len(ts) >= 3:  # 2회로는 우연히 일주일 간격인 거래와 구분되지 않는다
            weekday = statistics.mode(d.isoweekday() for d in days)
            cycle, pay_day, months = "WEEKLY", weekday, None
        elif 25 <= gap <= 35 and len({(d.year, d.month) for d in days}) == len(days):  # 한 달에 두 번 나오면 매월 일정이 아니다
            if all(_is_month_end(d) for d in days):
                pay_day = 31  # 말일 (30일까지 있는 달은 말일로 맞춰진다)
            elif max(d.day for d in days) - min(d.day for d in days) <= DAY_SPREAD:
                pay_day = int(statistics.median(d.day for d in days))
            else:
                continue
            cycle, months = "MONTHLY", None
        elif 80 <= gap <= 100:
            if max(d.day for d in days) - min(d.day for d in days) > DAY_SPREAD:
                continue
            cycle, pay_day = "QUARTERLY", int(statistics.median(d.day for d in days))
            m0 = days[-1].month
            months = ",".join(str(m) for m in sorted({(m0 - 1 + 3 * k) % 12 + 1 for k in range(4)}))
        else:
            continue
        kind = _kind(name, direction, cycle)
        if cycle == "QUARTERLY" and kind != "FIXED_COST":
            continue  # 분기 주기는 고정비로만 등록할 수 있다
        out.append(Candidate(name=name, direction=direction, kind=kind, pay_cycle=cycle, pay_day=pay_day, amount=mid, count=len(ts),
                             dates=days, varies=len(set(amounts)) > 1, months=months))
    return sorted(out, key=lambda c: (c.direction != "IN", -c.amount))


def last_balance(txns: list[Txn]) -> tuple[date, int] | None:
    """파일 마지막 거래 후 잔액. 현재 잔액을 맞출 때 쓴다.

    주의: 같은 날 거래끼리는 파일 순서를 그대로 두므로, 최신 거래가 위에 있는 파일이면 그날 첫 거래의 잔액이 나온다.
    """
    for t in reversed(txns):
        if t.balance is not None:
            return t.day, t.balance
    return None
