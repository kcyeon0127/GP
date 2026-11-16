"""ScenarioService (US-09): 등록 일정을 복사해 조건을 적용하고 기준안과 나란히 계산한다.

원본 cash_event와 기준안 forecast_run은 바꾸지 않는다 (AC-06). 시나리오 결과는 scenario_id가 붙은
forecast_run으로 저장되며, 조기경보(latest)는 scenario_id가 없는 실행만 보므로 홈 화면에 섞이지 않는다.
"""
import json
from dataclasses import asdict
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain import cashflow_engine
from ..domain import impact_path as ip
from ..domain import scenario as sc
from ..domain.constants import HORIZON_DAYS
from ..domain.enums import CashSource, ContractType, RateType
from ..models import Business, Contract, ForecastDaily, ForecastRun, Loan, Scenario
from ..repositories import graph_repository as g
from . import graph_service
from .forecast_service import events_of

KIND_OF_CONTRACT = {ContractType.SALES: "SALES", ContractType.PURCHASE: "PURCHASE"}


def items_of(s: Session, b: Business) -> list[sc.Item]:
    items = []
    for e in events_of(s, b.business_id):
        kind, party, principal = "FIXED_COST", None, None
        if e.source_type == CashSource.CONTRACT:
            c = s.get(Contract, e.source_id)
            kind, party = KIND_OF_CONTRACT.get(c.contract_type, "FIXED_COST"), c.counterparty_id
        elif e.source_type == CashSource.LOAN:
            loan = s.get(Loan, e.source_id)
            kind = "LOAN"
            principal = loan.principal if loan.rate_type == RateType.VARIABLE else None
        items.append(sc.Item(event_id=e.cash_event_id, due_date=e.due_date, amount=e.signed, label=e.label, kind=kind,
                             party_id=party, variable_principal=principal))
    return items


def _summary(f: cashflow_engine.Forecast) -> dict:
    return dict(signal=f.signal.value, first_shortage_date=f.first_shortage_date, shortage_amount=f.shortage_amount,
                max_shortage_amount=f.max_shortage_amount, min_balance=f.min_balance, min_balance_date=f.min_balance_date,
                first_below_safe_date=f.first_below_safe_date, daily=[{"date": d, "balance": bal} for d, bal in f.daily])


def _in_horizon(b: Business, d: date) -> bool:
    return 0 <= (d - b.base_date).days < HORIZON_DAYS


def compare(s: Session, b: Business, cond: sc.Conditions) -> dict:
    """기준안도 지금 일정으로 새로 계산한다: 저장된 최근 실행은 일정을 고친 뒤라 오래됐을 수 있어, 같은 일정끼리 비교되게 한다.

    GET comparison도 이 함수를 쓰므로 일정이 바뀌면 저장된 forecast_run과 값이 달라질 수 있다.
    "_forecast"는 run()이 저장에 쓰는 내부 값이라 응답 전에 뺀다.
    """
    items = items_of(s, b)
    after = sc.apply(items, cond)
    base_f = cashflow_engine.forecast(b.base_date, b.current_balance, b.safety_balance, [(i.due_date, i.amount) for i in items])
    scen_f = cashflow_engine.forecast(b.base_date, b.current_balance, b.safety_balance, [(i.due_date, i.amount) for i in after])
    base_bal, scen_bal = dict(base_f.daily), dict(scen_f.daily)
    # AC-02: 기준안에서는 낼 수 있었는데 시나리오에서는 그날 잔액이 0원 아래가 되는 지급
    # 기준안에서도 모자랐던 지급은 뺀다: 이 조건 때문에 새로 생긴 위험만 보여 주는 목록이다.
    new_short = [dict(event_id=a.event_id, date=a.due_date, label=a.label, amount=-a.amount, balance=scen_bal[a.due_date])
                 for a in after if a.amount < 0 and _in_horizon(b, a.due_date) and scen_bal[a.due_date] < 0 <= base_bal[a.due_date]]
    changes = [dict(event_id=a.event_id, label=a.label, before_date=i.due_date, after_date=a.due_date if _in_horizon(b, a.due_date) else None,
                    before_amount=i.amount, after_amount=a.amount)
               for i, a in zip(items, after) if (i.due_date, i.amount) != (a.due_date, a.amount) and _in_horizon(b, i.due_date)]
    return {"base": _summary(base_f), "scenario": _summary(scen_f), "new_shortages": new_short, "changes": changes, "_forecast": scen_f}


def run(s: Session, b: Business, cond: sc.Conditions) -> dict:
    out = compare(s, b, cond)
    f = out.pop("_forecast")
    scn = Scenario(business_id=b.business_id, shock_type="+".join(cond.kinds()), params=json.dumps(asdict(cond)))
    s.add(scn)
    s.flush()
    r = ForecastRun(business_id=b.business_id, scenario_id=scn.scenario_id, base_date=b.base_date, start_balance=b.current_balance,
                    safety_balance=b.safety_balance, first_shortage_date=f.first_shortage_date, shortage_amount=f.shortage_amount,
                    max_shortage_amount=f.max_shortage_amount, min_balance=f.min_balance, min_balance_date=f.min_balance_date,
                    first_below_safe_date=f.first_below_safe_date, signal=f.signal)
    s.add(r)
    s.flush()
    s.add_all([ForecastDaily(run_id=r.run_id, date=d, balance=bal) for d, bal in f.daily])
    s.flush()
    return {"scenario_id": scn.scenario_id, "run_id": r.run_id, "kinds": cond.kinds(), **out}


def conditions_of(scn: Scenario) -> sc.Conditions:
    return sc.Conditions(**json.loads(scn.params))


# ---------- US-08 위험 영향 경로 ----------
# 예정 입출금에서 금융지도 노드까지: 출처(계약·고정비·대출) → 근거 계약 → 거래처
CHAIN_CYPHER = """
MATCH (src)-[:GENERATES]->(e:CashEvent) WHERE e.cash_event_id IN $ids
OPTIONAL MATCH (src)-[:BASED_ON]->(base:Contract)
WITH e, src, CASE WHEN src:Contract THEN src ELSE base END AS k
OPTIONAL MATCH (c:Counterparty)-[:PARTY_TO]->(k)
RETURN e.cash_event_id AS event_id, labels(src)[0] AS src_label,
       coalesce(src.contract_id, src.fixed_cost_id, src.loan_id) AS src_id,
       k.contract_id AS contract_id, c.counterparty_id AS counterparty_id, c.name AS counterparty
"""
SRC_LABEL = {"CONTRACT": "Contract", "FIXED_COST": "FixedCost", "LOAN": "Loan"}


def _chains(s: Session, b: Business, ids: list[int]) -> dict[int, dict]:
    if not ids:
        return {}
    # 일정을 고치면 예정 입출금이 새 ID로 다시 만들어져 Neo4j에 없을 수 있다 (근거 조회와 같은 처리)
    found = {r["id"] for r in g.query("MATCH (e:CashEvent) WHERE e.cash_event_id IN $ids RETURN e.cash_event_id AS id", ids=ids)}
    if found != set(ids):
        graph_service.sync(s, b)
    return {r["event_id"]: r for r in g.query(CHAIN_CYPHER, ids=ids)}


def _nodes(step: dict, chain: dict | None) -> list[dict]:
    """금융지도에서 이 단계로 강조할 노드 (라벨 + 원본 ID). 화면은 노드 props의 같은 ID로 찾는다."""
    if step["role"] == "SHORTAGE":
        return [{"label": "Business"}]
    src = step["source"]
    out = [{"label": SRC_LABEL[src.source_type], "id": src.source_id}]
    if chain:
        if chain["contract_id"] and not (src.source_type == "CONTRACT" and chain["contract_id"] == src.source_id):
            out.append({"label": "Contract", "id": chain["contract_id"]})
        if chain["counterparty_id"]:
            out.append({"label": "Counterparty", "id": chain["counterparty_id"]})
    return out[::-1] if step["role"] == "CAUSE" else out  # 원인은 거래처 → 계약 순, 지급은 계약 → 거래처 순


def impact_path(s: Session, b: Business, scn: Scenario) -> dict:
    """GET /api/scenarios/{id}/impact-path. 기준안·시나리오는 compare()처럼 지금 등록 일정으로 다시 계산한다."""
    cond = conditions_of(scn)
    events = events_of(s, b.business_id)
    items = items_of(s, b)
    after = sc.apply(items, cond)
    base_f = cashflow_engine.forecast(b.base_date, b.current_balance, b.safety_balance, [(i.due_date, i.amount) for i in items])
    scen_f = cashflow_engine.forecast(b.base_date, b.current_balance, b.safety_balance, [(i.due_date, i.amount) for i in after])
    sources = {e.cash_event_id: ip.Source(e.source_type.value, e.source_id) for e in events}
    out = ip.build(b.base_date, items, after, base_f.daily, scen_f.daily, sources, cond.kinds())
    chains = _chains(s, b, sorted({eid for st in out["steps"] for eid in st["events"]}))
    steps = []
    for st in out["steps"]:
        chain = chains.get(st["events"][0]) if st["events"] else None
        label = st["label"]
        if st["role"] == "CAUSE" and chain and chain["counterparty"] and not label.startswith(chain["counterparty"]):
            label = f"{chain['counterparty']} {label}"
        src = st.pop("source")
        steps.append({**st, "label": label, "source": {"type": src.source_type, "id": src.source_id} if src else None, "nodes": _nodes({**st, "source": src}, chain)})
    return {"scenario_id": scn.scenario_id, "kinds": cond.kinds(), "shortage": out["shortage"], "steps": steps, "message": out["message"]}


def list_scenarios(s: Session, b: Business) -> list[dict]:
    rows = s.scalars(select(Scenario).where(Scenario.business_id == b.business_id).order_by(Scenario.scenario_id.desc()).limit(20))
    return [{"scenario_id": x.scenario_id, "kinds": conditions_of(x).kinds(), "params": json.loads(x.params)} for x in rows]
