"""ExplainService (US-18): 근거 목록과 계산 엔진 숫자만으로 근거 인용 설명을 만든다.

- 문장은 lab sLLM이 쓰고, domain.grounding 검증을 통과해야 내보낸다. LLM은 숫자를 만들지 않는다:
  쓸 수 있는 숫자는 근거 텍스트와 계산 결과(C1)에 이미 있는 값뿐이다.
- 검증에 실패하거나 서버가 꺼져 있으면 같은 근거로 만든 템플릿 문장으로 대체한다.
- 계약 조항 원문이 근거에 섞이므로 응답·근거 텍스트는 로그에 남기지 않는다. 실패 사유(ID·숫자)만 남긴다.
"""
import logging
from dataclasses import dataclass
from datetime import date

from ..domain import grounding
from ..domain.constants import EXPLAIN_EVIDENCE_CHARS
from ..repositories import llm_client

log = logging.getLogger(__name__)

CALC_ID = "C1"
FALLBACK_KO = {"LLM_DOWN": "AI 서버 꺼짐", "LLM_ERROR": "AI 응답 오류", "VERIFY_FAILED": "AI 응답 검증 실패", "HOLD": "판단 보류"}

SYSTEM = """너는 소상공인 자금 비서의 설명 작성기다. 아래 [근거]만 사용해서 한국어로 2~4문장을 쓴다.
규칙:
1. 모든 문장 끝에 그 문장의 근거 ID를 대괄호로 붙인다. 예: "...모자라요 [P1]." 계산 결과를 말하면 [C1]을 붙인다.
2. 금액·날짜·퍼센트는 근거에 적힌 값을 그대로 옮긴다. 새 숫자를 만들거나 더하기·빼기로 계산하지 않는다.
3. [근거] 목록에 없는 ID는 쓰지 않는다.
4. 제목·목록·머리말 없이 문장만 쓴다. 근거에 없는 사정이나 조언을 지어내지 않는다."""


@dataclass(frozen=True)
class Fact:
    label: str
    value: int | float | date | str
    unit: str = "won"  # won / date / pct / days / text


def fmt(f: Fact) -> str:
    v = f.value
    if f.unit == "won":
        return f"{v:,}원"
    if f.unit == "date":
        d = date.fromisoformat(v) if isinstance(v, str) else v
        return f"{d.month}/{d.day}"
    if f.unit == "pct":
        return f"{v:g}%"
    if f.unit == "days":
        return f"{v}일"
    return str(v)


def calc_evidence(facts: list[Fact]) -> dict:
    return {"id": CALC_ID, "type": "CALCULATION", "text": "계산 모듈 결과: " + ", ".join(f"{f.label} {fmt(f)}" for f in facts)}


def _allowed(evidence: list[dict]) -> grounding.Numbers:
    out = grounding.Numbers(won=[(0, 1)])  # "0원 아래로"는 늘 쓸 수 있다
    for e in evidence:
        out.add(grounding.extract(e["text"]))
    return out


def _messages(task: str, evidence: list[dict]) -> list[dict]:
    lines = "\n".join(f"[{e['id']}] {e['text'][:EXPLAIN_EVIDENCE_CHARS]}" for e in evidence)
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": f"[근거]\n{lines}\n\n[요청]\n{task}"}]


def _result(text: str, source: str, chk: grounding.Check, reason: str | None, problems: list[str], calc: dict) -> dict:
    return {"text": text, "source": source, "verified": chk.ok, "cited_ids": chk.cited, "fallback_reason": reason,
            "fallback_ko": FALLBACK_KO.get(reason), "problems": problems, "calc": calc}


def explain(task: str, evidence: list[dict], facts: list[Fact], template: list[str]) -> dict:
    """task: LLM에 줄 요청 문장. template: LLM이 실패했을 때 쓸 문장들 (같은 근거 ID를 인용해야 한다)."""
    calc = calc_evidence(facts)
    ev = [e for e in evidence if e.get("text")] + [calc]
    ids = {e["id"] for e in ev}
    allowed = _allowed(ev)
    tmpl = " ".join(template)

    def fallback(reason: str, problems: list[str]) -> dict:
        return _result(tmpl, "template", grounding.verify(tmpl, ids, allowed), reason, problems, calc)

    try:
        raw = llm_client.chat(_messages(task, ev))
    except llm_client.LLMUnavailable as e:
        log.info("설명 LLM 연결 실패 (%s): 템플릿 사용", e)
        return fallback("LLM_DOWN", [])
    except llm_client.LLMError as e:
        log.info("설명 LLM 응답 오류 (%s): 템플릿 사용", e)
        return fallback("LLM_ERROR", [str(e)])
    chk = grounding.verify(raw, ids, allowed)
    if not chk.ok:
        log.info("설명 검증 실패: %s", "; ".join(chk.problems))
        return fallback("VERIFY_FAILED", chk.problems)
    return _result(" ".join(chk.sentences), "llm", chk, None, [], calc)


def held(message: str, facts: list[Fact] | None = None) -> dict:
    """신뢰도가 낮아 설명을 보류할 때. 수치 없이 보류 문구만 낸다."""
    return {"text": message, "source": "template", "verified": False, "cited_ids": [], "fallback_reason": "HOLD",
            "fallback_ko": FALLBACK_KO["HOLD"], "problems": [], "calc": None}


# ---------- 화면별 사실(숫자)과 템플릿 ----------

def _ids(evidence: list[dict], prefix: str, n: int = 3) -> str:
    got = [e["id"] for e in evidence if e["id"].startswith(prefix)][:n]
    return "".join(f"[{i}]" for i in got)


def alert_facts(r) -> list[Fact]:
    """경보(ForecastRun)의 숫자. 화면에 이미 보이는 값만 쓴다."""
    out = [Fact("신호", {"RED": "위험", "YELLOW": "주의", "GREEN": "안전"}[r.signal.value], "text")]
    if r.first_shortage_date:
        out += [Fact("최초 부족일", r.first_shortage_date, "date"), Fact("부족액", r.shortage_amount)]
    if r.first_below_safe_date:
        out += [Fact("안전 잔액 미만 시작일", r.first_below_safe_date, "date"), Fact("안전 잔액", r.safety_balance)]
    out += [Fact("12주 최저 잔액", r.min_balance), Fact("최저 잔액일", r.min_balance_date, "date"), Fact("현재 잔액", r.start_balance)]
    return out


def alert_template(r, evidence: list[dict]) -> list[str]:
    s = []
    if r.signal.value == "RED":
        s.append(f"{fmt(Fact('', r.first_shortage_date, 'date'))}에 잔액이 0원 아래로 내려가 {r.shortage_amount:,}원이 부족할 것으로 계산됐어요 [C1].")
    else:
        s.append(f"{fmt(Fact('', r.first_below_safe_date, 'date'))}에 잔액이 안전 잔액 {r.safety_balance:,}원보다 적어질 것으로 계산됐어요 [C1].")
    if p := _ids(evidence, "P"):
        s.append(f"이 경보에 영향을 준 지급과 정산 일정은 거래관계 경로로 확인했어요 {p}.")
    if d := _ids(evidence, "D", 2):
        s.append(f"관련 계약서에서 지급 조건 조항을 함께 찾았어요 {d}.")
    s.append(f"12주 안 최저 잔액은 {fmt(Fact('', r.min_balance_date, 'date'))} {r.min_balance:,}원이에요 [C1].")
    return s


ALERT_TASK = "왜 이 자금 경보가 났는지 사장님께 설명해 주세요. 먼저 언제 얼마가 모자라는지, 다음으로 어떤 지급·정산 일정 때문인지 근거를 들어 말해 주세요."


# ---------- 경보 설명 + 신뢰도 (홈·이유 보기) ----------

GRAPH_DOWN_MSG = "근거 검색 서버(금융지도 그래프)에 연결되지 않았어요."
HOLD_LOW = "근거가 부족해 AI 설명을 보류했어요. 아래 정보를 등록하면 근거를 들어 설명해 드릴게요."


def gather_alert_evidence(s, r) -> tuple[dict, bool, bool]:
    """근거 검색(US-07). 그래프 서버가 꺼져도 예외 대신 빈 근거와 안내를 돌려준다. (결과, graph_down, docs_down)"""
    from . import evidence_service  # 순환 import 방지: evidence_service는 무거운 저장소들을 불러온다

    try:
        out = evidence_service.collect(s, r, save=False)
    except Exception as e:  # neo4j.exceptions.ServiceUnavailable 등
        log.warning("경보 근거 검색 실패: %s", type(e).__name__)
        s.rollback()
        return {"run_id": r.run_id, "evidence": [], "message": GRAPH_DOWN_MSG}, True, False
    return out, False, out["message"] == evidence_service.DOCS_DOWN


def for_alert(s, r, with_text: bool = True) -> dict:
    from . import confidence_service

    ev, graph_down, docs_down = gather_alert_evidence(s, r)
    conf = confidence_service.for_alert(s, r, ev["evidence"], graph_down, docs_down)
    out = {"run_id": r.run_id, "evidence": ev["evidence"], "message": ev["message"], "confidence": conf, "explanation": None}
    if not with_text or conf is None:
        return out
    if conf["level"] == "LOW":
        out["explanation"] = held(HOLD_LOW)
    else:
        out["explanation"] = explain(ALERT_TASK, ev["evidence"], alert_facts(r), alert_template(r, ev["evidence"]))
    return out
