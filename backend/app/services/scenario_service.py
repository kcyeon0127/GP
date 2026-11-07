"""ScenarioService (US-09): 등록 일정을 복사해 조건을 적용하고 기준안과 나란히 계산한다.

원본 cash_event와 기준안 forecast_run은 바꾸지 않는다 (AC-06). 시나리오 결과는 scenario_id가 붙은
forecast_run으로 저장되며, 조기경보(latest)는 scenario_id가 없는 실행만 보므로 홈 화면에 섞이지 않는다.
"""
import json
from dataclasses import asdict
from datetime import date

from sqlalchemy.orm import Session

from ..domain import cashflow_engine
from ..domain import scenario as sc
from ..domain.constants import HORIZON_DAYS
from ..domain.enums import CashSource, ContractType, RateType
from ..models import Business, Contract, ForecastDaily, ForecastRun, Loan, Scenario
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
