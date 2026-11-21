"""질문 → What-if 조건 (US-18 D). 규칙 파서와 LLM 계획 검증기. 둘 다 순수 함수다.

조건 모양은 POST /api/scenarios 입력과 같다 (US-09 2.2 동작 규칙):
  settlement_delay {counterparty: 매출처 이름, days: 1~60}, revenue_drop_pct (0, 90], cost_rise_pct (0, 100], rate_rise_pp (0, 10]
LLM이 만든 계획은 믿지 않는다: 키·타입·범위·등록된 이름을 모두 확인하고, 질문에 그 주제어가 실제로 있는지도 본다.
"""
import json
import re
from dataclasses import dataclass, field

LIMITS = {"revenue_drop_pct": (0, 90), "cost_rise_pct": (0, 100), "rate_rise_pp": (0, 10)}
MAX_DELAY = 60
TOPIC = {  # LLM이 질문에 없는 조건을 지어내지 않았는지 확인하는 주제어
    "revenue_drop_pct": r"매출|판매|손님",
    "cost_rise_pct": r"원가|매입|재료|식자재\s*값|납품\s*단가",
    "rate_rise_pp": r"금리|이자",
}
DELAY_WORDS = r"밀리|밀려|미뤄|미루|늦|지연|연체|안\s?들어|못\s?받"
UNSUPPORTED = [
    (r"폐업|부도|망하|망했|거래.*끊", "거래처 폐업·거래 중단은 아직 계산하지 않아요."),
    (r"대출.*(받|신청|빌리|추가|늘리)|(받|신청|빌리).*대출", "신규 대출은 아직 계산하지 않아요."),
]
NO_CONDITION = "시뮬레이션할 상황(정산 지연, 매출 감소, 원가 상승, 금리 상승)을 찾지 못했어요."


@dataclass
class Plan:
    delay: tuple[str, int] | None = None  # (매출처 이름, 지연 일수)
    revenue_drop_pct: float | None = None
    cost_rise_pct: float | None = None
    rate_rise_pp: float | None = None
    recognized: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    def empty(self) -> bool:
        return not (self.delay or self.revenue_drop_pct or self.cost_rise_pct or self.rate_rise_pp)

    def described(self) -> list[str]:
        out = []
        if self.delay:
            out.append(f"{self.delay[0]} 정산 {self.delay[1]}일 지연")
        if self.revenue_drop_pct:
            out.append(f"매출 {self.revenue_drop_pct:g}% 감소")
        if self.cost_rise_pct:
            out.append(f"원가(매입 대금) {self.cost_rise_pct:g}% 상승")
        if self.rate_rise_pp:
            out.append(f"변동금리 {self.rate_rise_pp:g}%p 상승")
        return out

    def conditions(self) -> dict:
        return {"settlement_delay": {"counterparty": self.delay[0], "days": self.delay[1]} if self.delay else None,
                "revenue_drop_pct": self.revenue_drop_pct, "cost_rise_pct": self.cost_rise_pct, "rate_rise_pp": self.rate_rise_pp}


def _mentions(text: str, name: str) -> bool:
    return name in text or (len(name) >= 3 and name[:2] in text)


def parse_days(t: str) -> int | None:
    words = [(r"일주일|1주일|한\s?주", 7), (r"이주일|2주일|두\s?주", 14), (r"삼주일|3주일|세\s?주", 21), (r"두\s?달|2\s?개월", 60), (r"한\s?달|1\s?개월", 30)]
    for pat, d in words:
        if re.search(pat, t):
            return d
    m = re.search(r"(\d+)\s*(일|주|개월|달)", t)
    if not m:
        return None
    n = int(m.group(1))
    return n if m.group(2) == "일" else n * 7 if m.group(2) == "주" else n * 30


def _pct(t: str, topic: str, default: float, rise: str) -> float | None:
    m = re.search(rf"(?:{topic})[^.%\d]*?(\d+(?:\.\d+)?)\s*(%p|%|퍼센트|프로|bp)", t, re.I)
    if m:
        v = float(m.group(1))
        return v / 100 if m.group(2).lower() == "bp" else v
    return default if re.search(rf"(?:{topic}).*(?:{rise})", t) else None


def rule_plan(text: str, sales: list[str], purchases: list[str], has_variable_loan: bool) -> Plan:
    """planner.ts 규칙 파서를 백엔드 조건(US-09)에 맞춰 옮겼다."""
    t = re.sub(r"\s+", " ", text).strip()
    p = Plan()
    for pat, msg in UNSUPPORTED:
        if re.search(pat, t):
            p.problems.append(msg)
    if re.search(DELAY_WORDS, t):
        party = next((n for n in sales if _mentions(t, n)), None)
        if party:
            days = parse_days(t) or 14
            if days > MAX_DELAY:
                p.problems.append(f"정산 지연은 {MAX_DELAY}일까지 계산해요. {MAX_DELAY}일로 계산했어요.")
                days = MAX_DELAY
            p.delay = (party, days)
            p.recognized += [f"매출처: {party}", f"지연: {days}일"]
        elif any(_mentions(t, n) for n in purchases):
            p.problems.append("정산 지연은 매출처(돈을 받는 곳)만 계산해요.")
        else:
            p.problems.append("어느 매출처의 정산인지 알 수 없어요." + (f" 등록된 매출처: {', '.join(sales)}" if sales else " 매출처를 먼저 등록하세요."))
    for key, default, rise, label in [("revenue_drop_pct", 20, "줄|감소|하락|떨어|빠지", "매출 감소"), ("cost_rise_pct", 10, "오르|올라|인상|상승|늘", "원가 상승"),
                                      ("rate_rise_pp", 1, "오르|올라|인상|상승", "금리 상승")]:
        v = _pct(t, TOPIC[key], default, rise)
        if v is None:
            continue
        lo, hi = LIMITS[key]
        if not lo < v <= hi:
            p.problems.append(f"{label}은 {hi}{'%p' if key == 'rate_rise_pp' else '%'}까지 계산해요.")
            continue
        setattr(p, key, v)
        p.recognized.append(f"{label}: {v:g}{'%p' if key == 'rate_rise_pp' else '%'}")
    if p.rate_rise_pp and not has_variable_loan:
        p.problems.append("변동금리 대출이 등록되어 있지 않아 금리 상승 영향이 없어요.")
    if p.empty() and not p.problems:
        p.problems.append(NO_CONDITION)
    return p


class PlanRejected(ValueError):
    pass


def _num(v, lo: float, hi: float, integer: bool = False) -> bool:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or (integer and not float(v).is_integer()):
        return False
    return lo < v <= hi


def parse_llm_json(raw: str) -> dict:
    s = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M)
    i, j = s.find("{"), s.rfind("}")
    if i < 0 or j <= i:
        raise PlanRejected("JSON 없음")
    try:
        obj = json.loads(s[i:j + 1])
    except json.JSONDecodeError as e:
        raise PlanRejected("JSON 형식 오류") from e
    if not isinstance(obj, dict):
        raise PlanRejected("JSON 객체 아님")
    return obj


def validate_llm(obj: dict, query: str, sales: list[str], has_variable_loan: bool) -> Plan:
    """LLM 계획을 엄격히 검사한다. 하나라도 어긋나면 PlanRejected (규칙 파서로 대체)."""
    allowed = {"settlement_delay", "revenue_drop_pct", "cost_rise_pct", "rate_rise_pp", "unsupported"}
    if extra := set(obj) - allowed:
        raise PlanRejected(f"모르는 키 {sorted(extra)}")
    p = Plan()
    d = obj.get("settlement_delay")
    if d is not None:
        if not isinstance(d, dict) or set(d) != {"counterparty", "days"}:
            raise PlanRejected("settlement_delay 모양 오류")
        if d["counterparty"] not in sales:
            raise PlanRejected("등록되지 않은 매출처")
        if not _mentions(query, d["counterparty"]) or not re.search(DELAY_WORDS, query):
            raise PlanRejected("질문에 없는 정산 지연")
        if not _num(d["days"], 0, MAX_DELAY, integer=True):
            raise PlanRejected("지연 일수 범위 오류")
        p.delay = (d["counterparty"], int(d["days"]))
        p.recognized += [f"매출처: {p.delay[0]}", f"지연: {p.delay[1]}일"]
    for key, label in [("revenue_drop_pct", "매출 감소"), ("cost_rise_pct", "원가 상승"), ("rate_rise_pp", "금리 상승")]:
        v = obj.get(key)
        if v is None:
            continue
        if not _num(v, *LIMITS[key]):
            raise PlanRejected(f"{key} 범위 오류")
        if not re.search(TOPIC[key], query):
            raise PlanRejected(f"질문에 없는 {label}")
        setattr(p, key, float(v))
        p.recognized.append(f"{label}: {float(v):g}{'%p' if key == 'rate_rise_pp' else '%'}")
    un = obj.get("unsupported") or []
    if not isinstance(un, list) or not all(isinstance(x, str) and len(x) <= 80 for x in un):
        raise PlanRejected("unsupported 모양 오류")
    p.problems += [f"계산하지 못한 부분: {x}" for x in un if x.strip()]
    if p.rate_rise_pp and not has_variable_loan:
        p.problems.append("변동금리 대출이 등록되어 있지 않아 금리 상승 영향이 없어요.")
    if p.empty():
        raise PlanRejected("조건 없음")
    return p
