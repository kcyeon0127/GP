"""근거 인용 검증 (US-18). LLM이 쓴 설명이 주어진 근거 ID와 숫자만 쓰는지 확인하는 순수 함수다.

검사 규칙:
(a) 모든 문장이 근거 ID를 1개 이상 대괄호로 인용한다. 예: "...모자라요 [P1]."
(b) 문장 속 금액·날짜·퍼센트는 모두 입력 근거 텍스트(계산 결과 C1 포함)에 있는 값이다.
(c) 근거 목록에 없는 ID는 쓰지 않는다.
그 밖에 한자·영문 위주 응답(소형 모델이 가끔 중국어로 답한다), 너무 길거나 빈 응답도 거부한다.
"""
import re
from dataclasses import dataclass, field

from .constants import EXPLAIN_MAX_CHARS, EXPLAIN_MAX_SENTENCES

CITE = re.compile(r"\[([A-Z]\d+(?:\s*[,·/]\s*[A-Z]\d+)*)\]")
ID = re.compile(r"[A-Z]\d+")
UNIT = {"억": 100_000_000, "천만": 10_000_000, "백만": 1_000_000, "만": 10_000}

# 순서가 중요하다: 앞의 패턴이 잡은 부분은 지워서 뒤 패턴이 다시 세지 않게 한다.
PATTERNS = [
    ("date", re.compile(r"\b\d{4}-(\d{1,2})-(\d{1,2})\b")),
    ("date", re.compile(r"(\d{1,2})\s*월\s*(\d{1,2})\s*일")),
    ("date", re.compile(r"(?<![\d,./])(\d{1,2})/(\d{1,2})(?![\d/])")),
    ("won2", re.compile(r"(\d+)\s*억\s*(\d[\d,]*)\s*만\s*원")),
    ("won", re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(억|천만|백만|만)?\s*원")),
    ("pct", re.compile(r"(\d+(?:\.\d+)?)\s*(?:%p|%포인트|%|퍼센트|프로)")),
    ("won", re.compile(r"(\d{1,3}(?:,\d{3})+)()")),  # 단위 없이 쓴 큰 금액 1,500,000
]


@dataclass
class Numbers:
    dates: set = field(default_factory=set)  # (월, 일)
    won: list = field(default_factory=list)  # (값, 허용 오차)
    pct: set = field(default_factory=set)

    def add(self, other: "Numbers") -> None:
        self.dates |= other.dates
        self.won += other.won
        self.pct |= other.pct


def extract(text: str) -> Numbers:
    """텍스트에서 날짜·금액·퍼센트를 뽑는다. 금액은 부호를 떼고 본다 (잔액 -50만 원과 부족액 50만 원은 같은 숫자)."""
    out = Numbers()
    for kind, pat in PATTERNS:
        def take(m: re.Match) -> str:
            if kind == "date":
                out.dates.add((int(m.group(1)), int(m.group(2))))
            elif kind == "won2":
                out.won.append((int(m.group(1)) * UNIT["억"] + int(m.group(2).replace(",", "")) * UNIT["만"], UNIT["만"]))
            elif kind == "won":
                unit = UNIT.get(m.group(2) or "", 1)
                out.won.append((round(float(m.group(1).replace(",", "")) * unit), unit))
            else:
                out.pct.add(float(m.group(1)))
            return " " * len(m.group(0))
        text = pat.sub(take, text)
    return out


def _won_ok(value: int, unit: int, allowed: list) -> bool:
    """단위 없이 쓴 금액은 정확히 같아야 한다. '152만 원'처럼 단위로 줄여 쓴 금액은 반올림·버림 차이만 허용한다."""
    if unit == 1:
        return any(value == a for a, _ in allowed)
    return any(abs(value - a) < unit for a, _ in allowed)


def unknown_numbers(text: str, allowed: Numbers) -> list[str]:
    got = extract(text)
    bad = [f"{m}/{d}" for m, d in sorted(got.dates - allowed.dates)]
    bad += [f"{v:,}원" for v, u in got.won if not _won_ok(v, u, allowed.won)]
    bad += [f"{p:g}%" for p in sorted(got.pct - allowed.pct)]
    return bad


def split_sentences(text: str) -> list[str]:
    """문장 단위로 나눈다. 마침표 뒤에 따로 붙은 인용([P1])은 앞 문장에 붙인다. 목록 기호·강조 표시는 지운다."""
    text = re.sub(r"\*\*|__|`", "", text)
    lines = [re.sub(r"^\s*(?:[-*•]|\d+[.)])\s+", "", ln) for ln in text.splitlines()]
    parts = [p.strip() for ln in lines for p in re.split(r"(?<=[.!?])\s+", ln) if p.strip()]
    out: list[str] = []
    for p in parts:
        if out and CITE.sub("", p).strip(" .") == "":
            out[-1] = f"{out[-1]} {p}"
        else:
            out.append(p)
    return out


def cited_ids(sentence: str) -> list[str]:
    return [i for inner in CITE.findall(sentence) for i in ID.findall(inner)]


@dataclass
class Check:
    ok: bool
    sentences: list[str]
    cited: list[str]
    problems: list[str]


def verify(text: str, ids: set[str], allowed: Numbers, max_sentences: int = EXPLAIN_MAX_SENTENCES) -> Check:
    sentences = split_sentences(text)
    problems: list[str] = []
    if not sentences:
        problems.append("빈 응답")
    if len(sentences) > max_sentences:
        problems.append(f"문장 수 {len(sentences)}개 (최대 {max_sentences}개)")
    if len(text) > EXPLAIN_MAX_CHARS:
        problems.append(f"길이 {len(text)}자 (최대 {EXPLAIN_MAX_CHARS}자)")
    hangul = len(re.findall(r"[가-힣]", text))
    if re.search(r"[一-鿿぀-ヿ]", text) or hangul < len(re.sub(r"\W|\d|_", "", CITE.sub("", text))) * 0.5:
        problems.append("한국어가 아닌 응답")
    cited: list[str] = []
    for n, s in enumerate(sentences, 1):
        cs = cited_ids(s)
        if not cs:
            problems.append(f"{n}번째 문장에 근거 ID 없음")
        for c in cs:
            if c not in ids:
                problems.append(f"없는 근거 ID {c}")
            elif c not in cited:
                cited.append(c)
    bad = unknown_numbers(CITE.sub(" ", text), allowed)
    if bad:
        problems.append("근거에 없는 숫자 " + ", ".join(bad))
    return Check(ok=not problems, sentences=sentences, cited=cited, problems=list(dict.fromkeys(problems)))
