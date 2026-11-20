"""AskService (US-18 D): 말로 물어보기. 질문 → What-if 조건 → 시나리오 계산(US-09) → 경로 근거 → 근거 인용 설명 + 신뢰도.

1. lab sLLM이 질문을 조건 JSON으로 바꾼다. 실제 DB의 매출처 이름 목록을 제약으로 주고, 결과는 ask_rules.validate_llm으로 엄격히 검사한다.
   서버가 꺼졌거나 검사에 실패하면 규칙 파서(ask_rules.rule_plan)로 대체한다.
2. 계산은 scenario_service.run (US-09)이 한다. LLM은 숫자를 만들지 않는다.
3. 바뀐 일정·새로 모자라는 지급의 금융지도 경로를 P 근거로 붙이고, explain_service로 설명한다.
"""
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain import ask_rules as ar
from ..domain import scenario as sc
from ..domain.enums import ContractType, RateType
from ..models import Business, Contract, Counterparty, Loan
from ..repositories import llm_client
from . import confidence_service, evidence_service, explain_service, scenario_service

log = logging.getLogger(__name__)

PLAN_SYSTEM = """너는 사장님 질문을 자금 시뮬레이션 조건 JSON으로 바꾸는 변환기다. JSON 객체 하나만 출력한다.
스키마:
{"settlement_delay": {"counterparty": "매출처 이름", "days": 1~60 정수} 또는 null,
 "revenue_drop_pct": 0 초과 90 이하 숫자 또는 null,
 "cost_rise_pct": 0 초과 100 이하 숫자 또는 null,
 "rate_rise_pp": 0 초과 10 이하 숫자 또는 null,
 "unsupported": [계산할 수 없는 부분을 짧게]}
규칙: 매출처 이름은 주어진 목록에서 그대로 고른다. 질문에 없는 조건은 null로 둔다. 1주=7일, 2주=14일, 한 달=30일.
신규 대출, 거래처 폐업은 unsupported에 넣는다."""
HOLD_LOW = "질문을 뒷받침할 근거가 부족해 AI 설명을 보류했어요. 아래 정보를 등록하면 근거를 들어 설명해 드릴게요."
GRAPH_DOWN = "근거 검색 서버(금융지도 그래프)에 연결되지 않아 경로 근거 없이 계산 결과만 보여 드려요."


def _names(s: Session, b: Business) -> tuple[dict[str, int], list[str], bool]:
    rows = s.execute(select(Counterparty.counterparty_id, Counterparty.name, Contract.contract_type).join(Contract)
                     .where(Counterparty.business_id == b.business_id)).all()
    sales = {n: cid for cid, n, t in rows if t == ContractType.SALES}
    purchases = sorted({n for _, n, t in rows if t == ContractType.PURCHASE})
    has_var = bool(s.scalar(select(Loan.loan_id).where(Loan.business_id == b.business_id, Loan.rate_type == RateType.VARIABLE).limit(1)))
    return sales, purchases, has_var


def plan(query: str, sales: list[str], purchases: list[str], has_var: bool) -> tuple[ar.Plan, str, str | None]:
    """(계획, source llm|rule, LLM을 쓰지 못한 이유)."""
    msgs = [{"role": "system", "content": PLAN_SYSTEM},
            {"role": "user", "content": f"매출처 목록: {', '.join(sales) or '없음'}\n변동금리 대출: {'있음' if has_var else '없음'}\n질문: {query}"}]
    try:
        raw = llm_client.chat(msgs, max_tokens=200, temperature=0.0, json_mode=True)
        return ar.validate_llm(ar.parse_llm_json(raw), query, sales, has_var), "llm", None
    except llm_client.LLMUnavailable:
        reason = "LLM_DOWN"
    except llm_client.LLMError:
        reason = "LLM_ERROR"
    except ar.PlanRejected as e:
        log.info("질문 계획 검증 실패: %s", e)
        reason = "VERIFY_FAILED"
    return ar.rule_plan(query, sales, purchases, has_var), "rule", reason


def _facts(p: ar.Plan, out: dict) -> list[explain_service.Fact]:
    F = explain_service.Fact
    base, scen = out["base"], out["scenario"]
    facts = [F("가정", ", ".join(p.described()), "text")]
    if p.rate_rise_pp:
        facts.append(F("금리 상승폭", f"{p.rate_rise_pp:g}%p", "text"))
    facts += [F("기준안 12주 최저 잔액", base["min_balance"]), F("시나리오 12주 최저 잔액", scen["min_balance"]),
              F("시나리오 최저 잔액일", scen["min_balance_date"], "date"), F("최저 잔액 변화", scen["min_balance"] - base["min_balance"])]
    if base["first_shortage_date"]:
        facts.append(F("기준안 최초 부족일", base["first_shortage_date"], "date"))
    if scen["first_shortage_date"]:
        facts += [F("시나리오 최초 부족일", scen["first_shortage_date"], "date"), F("시나리오 부족액", scen["shortage_amount"])]
    facts.append(F("새로 모자라는 지급", f"{len(out['new_shortages'])}건", "text"))
    return facts


def _template(p: ar.Plan, out: dict, evidence: list[dict]) -> list[str]:
    base, scen = out["base"], out["scenario"]
    fd = lambda d: explain_service.fmt(explain_service.Fact("", d, "date"))  # noqa: E731
    t = [f"{', '.join(p.described())}을(를) 가정해 다시 계산했어요 [C1]."]
    if scen["first_shortage_date"]:
        t.append(f"그러면 {fd(scen['first_shortage_date'])}에 잔액이 0원 아래로 내려가 {scen['shortage_amount']:,}원이 부족해요 [C1].")
    else:
        t.append("12주 안에 잔액이 0원 아래로 내려가지 않아요 [C1].")
    t.append(f"12주 최저 잔액은 기준안 {base['min_balance']:,}원에서 {scen['min_balance']:,}원으로 바뀌어요 [C1].")
    if ps := "".join(f"[{e['id']}]" for e in evidence[:3]):
        t.append(f"영향을 받는 일정은 거래관계 경로로 확인했어요 {ps}.")
    return t


def ask(s: Session, b: Business, query: str) -> dict:
    sales, purchases, has_var = _names(s, b)
    p, source, reason = plan(query, list(sales), purchases, has_var)
    plan_out = {"source": source, "fallback_reason": reason, "conditions": p.conditions(), "described": p.described(),
                "recognized": p.recognized, "problems": p.problems}
    if p.empty():
        return {"query": query, "plan": plan_out, "result": None, "evidence": [], "explanation": None, "confidence": None,
                "message": "질문을 시뮬레이션 조건으로 바꾸지 못했어요."}
    cond = sc.Conditions(delay_counterparty_id=sales[p.delay[0]] if p.delay else None, delay_days=p.delay[1] if p.delay else 0,
                         revenue_drop_pct=p.revenue_drop_pct or 0, cost_rise_pct=p.cost_rise_pct or 0, rate_rise_pp=p.rate_rise_pp or 0)
    out = scenario_service.run(s, b, cond)
    notes = {x["event_id"]: "조건 때문에 새로 모자라는 지급" for x in out["new_shortages"]}
    for x in out["changes"]:
        notes.setdefault(x["event_id"], "조건으로 바뀌는 일정")
    graph_down, message = False, None
    try:
        evidence = evidence_service.paths_for(s, b, notes)
    except Exception as e:  # neo4j.exceptions.ServiceUnavailable 등
        log.warning("질문 경로 근거 실패: %s", type(e).__name__)
        evidence, graph_down, message = [], True, GRAPH_DOWN
    parse_ok = not p.problems
    conf = confidence_service.for_question(
        s, b, list(notes)[:6], evidence, 1.0 if parse_ok else 0.5,
        "질문을 모두 계산 조건으로 바꿨어요." if parse_ok else "질문 일부는 계산 조건으로 바꾸지 못했어요.", p.problems, graph_down)
    if conf["level"] == "LOW":
        explanation = explain_service.held(HOLD_LOW)
    else:
        task = f"사장님 질문: \"{query}\"\n위 조건으로 다시 계산한 결과로 질문에 답해 주세요. 먼저 부족 여부와 날짜·금액을, 다음으로 영향을 받는 일정을 근거로 말해 주세요."
        explanation = explain_service.explain(task, evidence, _facts(p, out), _template(p, out, evidence))
    return {"query": query, "plan": plan_out, "scenario_id": out["scenario_id"], "run_id": out["run_id"],
            "result": {"base": out["base"], "scenario": out["scenario"], "new_shortages": out["new_shortages"], "changes": out["changes"]},
            "evidence": evidence, "explanation": explanation, "confidence": conf, "message": message}

