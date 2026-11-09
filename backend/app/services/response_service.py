"""ResponseService (US-10·11): 경보에 대한 대응안 후보를 만들고, 대표가 승인한 안만 일정에 반영한다.

- 후보와 효과(최저 잔액·부족일)는 domain.response 규칙과 cashflow_engine이 만든다. LLM은 숫자를 만들지 않는다.
- 설명에는 같은 계산(run)의 근거 ID(P=거래관계 경로, D=계약 문서 조각)를 붙인다 (AC-02).
- 제시만으로는 아무것도 바뀌지 않는다. 승인하면 그 출처의 예정 입출금을 다시 만들고 예상 잔액을 새로 계산한다 (AC-03).
- US-11 판단 보류: 지급 조건을 바꾸자는 안이므로 그 계약의 문서 조항(D 근거)이 있어야 제시한다.
  조항이 없는 후보는 수치 없이 "근거 부족"으로만 알리고, 제시할 후보가 하나도 없으면 판단을 보류한다.
  경보일 뒤에 들어올 돈이 하나도 등록되지 않아 옮길 날이 없을 때도 보류하고 무엇을 등록할지 안내한다.
"""
import json
import logging
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..domain import response as rp
from ..domain.enums import CashDirection, CashSource, ContractType, PlanStatus, SignalLevel
from ..models import Business, CashEvent, Contract, Document, DocumentChunk, FixedCost, ForecastRun, Loan, ResponsePlan
from . import evidence_service, forecast_service, schedule_service

log = logging.getLogger(__name__)

SIGNAL_KO = {SignalLevel.RED: "위험", SignalLevel.YELLOW: "주의", SignalLevel.GREEN: "안전"}
KIND_KO = {"PAY_DATE_SHIFT": "결제일 조정", "PURCHASE_SPLIT": "매입 분할", "EXPENSE_SHIFT": "지출 조정", "LOAN_CHECK": "상환 일정 점검"}
CAUTION = {
    "PAY_DATE_SHIFT": "매입처 동의가 있어야 해요. 계약서의 지급기일·지연이자 조항을 먼저 확인하세요.",
    "PURCHASE_SPLIT": "매입처 동의가 있어야 해요. 나머지 금액을 내는 날짜를 꼭 지킬 수 있는지 확인하세요.",
    "EXPENSE_SHIFT": "받는 곳과 미리 협의해야 해요. 늦어지면 연체료가 붙는지 확인하세요.",
    "LOAN_CHECK": "은행과 먼저 협의해야 해요. 협의 없이 늦으면 연체로 처리되어 지연배상금이나 기한이익상실 조항이 적용될 수 있어요.",
}
NO_ALERT = "지금은 4주 안에 대응이 필요한 경보가 없어요."
NO_PLAN = "일정의 날짜만 옮겨서는 부족을 줄일 수 있는 안을 찾지 못했어요."
# US-11 판단 보류 안내. 보류할 때는 잔액 변화 같은 수치를 내보내지 않는다 (AC-04).
HOLD_NO_INFLOW = "경보일 뒤 12주 안에 들어올 돈이 등록되어 있지 않아 지급을 옮길 날짜를 정할 수 없어요."
HOLD_NO_EVIDENCE = "후보는 찾았지만 계약 근거가 없어 판단을 보류했어요. 아래 정보를 등록한 뒤 다시 요청하세요."
NEED_SALES = "매출처의 정산 일정(거래처·결제 조건)을 등록하세요."
SERVER_DOWN = "근거 검색 서버(금융지도 그래프)에 연결되지 않았어요. 서버를 켠 뒤 다시 요청하세요."
DOCS_SERVER_DOWN = "계약 문서 검색 서버(임베딩)에 연결되지 않았어요. 연결한 뒤 다시 요청하세요."


def _kind_of(s: Session, e: CashEvent) -> str:
    if e.source_type == CashSource.CONTRACT:
        c = s.get(Contract, e.source_id)
        return {ContractType.SALES: "SALES", ContractType.PURCHASE: "PURCHASE"}.get(c.contract_type, "FIXED_COST")
    return "LOAN" if e.source_type == CashSource.LOAN else "FIXED_COST"


def _contract_of(s: Session, e: CashEvent) -> int | None:
    if e.source_type == CashSource.CONTRACT:
        return e.source_id
    obj = s.get(FixedCost if e.source_type == CashSource.FIXED_COST else Loan, e.source_id)
    return obj.contract_id if obj else None


def _adjusted_keys(s: Session, b: Business) -> set[tuple]:
    """이미 승인한 안이 만든 행. (출처, 출처 ID, 날짜)로 찾는다."""
    return {(p.source_type, p.source_id, x["due_date"]) for p in schedule_service.approved_plans(s, b.business_id) for x in json.loads(p.parts)}


def _summary(f) -> dict:
    return dict(signal=f.signal.value, first_shortage_date=f.first_shortage_date and f.first_shortage_date.isoformat(),
                shortage_amount=f.shortage_amount, min_balance=f.min_balance, min_balance_date=f.min_balance_date.isoformat(),
                alert_min_balance=min(b for _, b in f.daily[:rp.ALERT_DAYS]),
                daily=[{"date": d.isoformat(), "balance": bal} for d, bal in f.daily])


def _evidence(s: Session, r: ForecastRun) -> tuple[list[dict], str | None]:
    """근거 검색(US-07)을 그대로 쓴다. 두 번째 값은 서버 문제로 문서 근거를 못 본 경우의 안내다."""
    try:
        out = evidence_service.collect(s, r)
    except Exception as e:  # neo4j.exceptions.ServiceUnavailable 등
        log.warning("대응안 근거 검색 실패: %s", e)
        return [], SERVER_DOWN
    return out["evidence"], DOCS_SERVER_DOWN if out["message"] == evidence_service.DOCS_DOWN else None


def _missing(s: Session, b: Business, target: CashEvent, server_msg: str | None) -> str:
    """이 후보에 문서 근거가 없는 이유를 사장님이 고칠 수 있는 말로 바꾼다 (US-11 AC-01)."""
    if server_msg:
        return server_msg
    cid = _contract_of(s, target)
    if cid is None:
        return f"'{target.label}'의 받는 곳과 계약서가 등록되지 않았어요."
    c = s.get(Contract, cid)
    party = c.counterparty.name if c and c.counterparty else target.label
    doc = s.scalar(select(Document).where(Document.business_id == b.business_id, Document.contract_id == cid).limit(1))
    if doc is None:
        return f"'{party}' 계약서가 등록되지 않았어요."
    return f"'{doc.title}'에서 지급 조건 조항을 찾지 못했어요."


def _no_inflow_after(rows: list[CashEvent], b: Business, trigger) -> bool:
    end = b.base_date.toordinal() + rp.HORIZON_DAYS - 1
    return not any(e.direction == CashDirection.IN and trigger < e.due_date and e.due_date.toordinal() <= end for e in rows)


def _refs_for(s: Session, evidence: list[dict], target: CashEvent, in_events: list[CashEvent]) -> list[str]:
    """이 안과 관련된 근거 ID: 옮기는 지급의 경로, 옮긴 날 들어오는 돈의 경로, 옮기는 지급의 계약 조항."""
    want = {f"event:{target.cash_event_id}"} | {f"event:{e.cash_event_id}" for e in in_events}
    cid = _contract_of(s, target)
    chunk_contract = {}
    keys = [ev["ref"] for ev in evidence if ev["type"] == "DOCUMENT_CHUNK"]
    if keys:
        chunk_contract = dict(s.execute(select(DocumentChunk.key, DocumentChunk.contract_id).where(DocumentChunk.key.in_(keys))).all())
    return [ev["id"] for ev in evidence if ev["ref"] in want or (cid is not None and ev["type"] == "DOCUMENT_CHUNK" and chunk_contract.get(ev["ref"]) == cid)]


def _texts(plan: rp.Plan, base, target: CashEvent, in_labels: list[str], refs: list[str]) -> tuple[str, str]:
    t, amt = target, target.amount
    new = plan.parts[-1]
    by = f"{new.due_date:%m/%d} {', '.join(in_labels)} 입금 뒤" if in_labels else f"{new.due_date:%m/%d}"
    if plan.kind == "PURCHASE_SPLIT":
        title = f"{t.label} 분할 지급 요청"
        how = f"{t.due_date:%m/%d} {t.label} {amt:,}원 중 {plan.parts[0].amount:,}원만 그날 내고, 나머지 {new.amount:,}원은 {by}에 냅니다."
    elif plan.kind == "LOAN_CHECK":
        title = f"{t.label}일 조정 협의"
        how = f"{t.due_date:%m/%d} {t.label} {amt:,}원을 {plan.shift_days}일 뒤 {by}로 옮길 수 있는지 은행과 점검합니다."
    else:
        title = f"{t.label} {'결제일 조정 요청' if plan.kind == 'PAY_DATE_SHIFT' else '지급일 조정'}"
        how = f"{t.due_date:%m/%d} {t.label} {amt:,}원을 {plan.shift_days}일 미뤄 {by}에 냅니다."
    f = plan.forecast
    effect = f"4주 신호 {SIGNAL_KO[base.signal]} → {SIGNAL_KO[f.signal]}, 4주 최저 잔액 {_summary(base)['alert_min_balance']:,}원 → {_summary(f)['alert_min_balance']:,}원"
    effect += f", 최초 부족일 {f.first_shortage_date:%m/%d}." if f.first_shortage_date else ", 12주 안 부족 없음."
    return title, f"{how} {effect}" + (f" (근거 {', '.join(refs)})" if refs else "")


def _dto(p: ResponsePlan, evidence_text: dict[str, str] | None = None) -> dict:
    refs = json.loads(p.evidence_ids)
    return dict(plan_id=p.plan_id, run_id=p.run_id, kind=p.kind, kind_ko=KIND_KO[p.kind], title=p.title, description=p.description, caution=p.caution,
                target=dict(source_type=p.source_type.value, source_id=p.source_id, date=p.original_date.isoformat(), amount=p.original_amount),
                parts=json.loads(p.parts), result=json.loads(p.result), status=p.status.value,
                evidence=[{"id": i, "text": (evidence_text or {}).get(i)} for i in refs], evidence_missing=not refs,
                decided_at=p.decided_at.isoformat() if p.decided_at else None)


def propose(s: Session, b: Business) -> dict:
    r = forecast_service.run(s, b)  # 지금 일정으로 새로 계산한다: 일정을 고친 뒤 오래된 경보로 후보를 만들지 않게
    s.execute(update(ResponsePlan).where(ResponsePlan.business_id == b.business_id, ResponsePlan.status == PlanStatus.PROPOSED)
              .values(status=PlanStatus.EXPIRED))
    rows = forecast_service.events_of(s, b.business_id)
    adjusted = _adjusted_keys(s, b)
    by_id = {e.cash_event_id: e for e in rows}
    events = [rp.Event(event_id=e.cash_event_id, due_date=e.due_date, amount=e.signed, label=e.label, kind=_kind_of(s, e),
                       adjusted=(e.source_type, e.source_id, e.due_date.isoformat()) in adjusted) for e in rows]
    st = rp.Setting(b.base_date, b.current_balance, b.safety_balance)
    base, plans = rp.propose(events, st)
    out = {"run_id": r.run_id, "base": _summary(base), "plans": [], "withheld": [], "evidence": [], "hold": None, "message": None}
    if r.signal == SignalLevel.GREEN:
        out["message"] = NO_ALERT
        return out
    if not plans:
        if _no_inflow_after(rows, b, rp.trigger_date(base)):
            return _hold(out, base, "NO_INFLOW", HOLD_NO_INFLOW, [NEED_SALES])
        out["message"] = NO_PLAN
        return out
    evidence, server_msg = _evidence(s, r)
    texts = {ev["id"]: ev["text"] for ev in evidence}
    for plan in plans:
        target = by_id[plan.target.event_id]
        new_date = plan.parts[-1].due_date
        in_events = [e for e in rows if e.direction == CashDirection.IN and e.due_date == new_date]
        refs = _refs_for(s, evidence, target, in_events)
        title, desc = _texts(plan, base, target, [e.label for e in in_events], refs)
        if not any(x.startswith("D") for x in refs):
            # 수치는 빼고 무엇이 없는지만 알린다 (US-11 AC-03·04). 저장하지 않으므로 승인할 수도 없다.
            out["withheld"].append(dict(kind=plan.kind, kind_ko=KIND_KO[plan.kind], title=title, missing=_missing(s, b, target, server_msg)))
            continue
        row = ResponsePlan(business_id=b.business_id, run_id=r.run_id, kind=plan.kind, title=title, description=desc, caution=CAUTION[plan.kind],
                           source_type=target.source_type, source_id=target.source_id, original_date=target.due_date, original_amount=target.amount,
                           parts=json.dumps([{"due_date": x.due_date.isoformat(), "amount": x.amount} for x in plan.parts]),
                           result=json.dumps(_summary(plan.forecast)), evidence_ids=json.dumps(refs), status=PlanStatus.PROPOSED)
        s.add(row)
        s.flush()
        out["plans"].append(_dto(row, texts))
    if not out["plans"]:
        missing = list(dict.fromkeys(w["missing"] for w in out["withheld"]))
        return _hold(out, base, "NO_EVIDENCE", HOLD_NO_EVIDENCE, missing)
    out["evidence"] = evidence
    return out


def _hold(out: dict, base, code: str, message: str, missing: list[str]) -> dict:
    """판단 보류: 기준안도 신호만 남기고 잔액·부족액 같은 수치는 내보내지 않는다 (US-11 AC-04)."""
    out["base"] = {"signal": base.signal.value}
    out["hold"] = {"code": code, "message": message, "missing": missing}
    return out


class PlanConflict(Exception):
    pass


def _get(s: Session, b: Business, plan_id: int) -> ResponsePlan | None:
    p = s.get(ResponsePlan, plan_id)
    return p if p and p.business_id == b.business_id else None


def approve(s: Session, b: Business, p: ResponsePlan) -> ForecastRun:
    if p.status != PlanStatus.PROPOSED:
        raise PlanConflict("이미 처리했거나 다시 요청해서 밀려난 대응안이에요. 대응안을 다시 요청하세요.")
    still = s.scalar(select(CashEvent.cash_event_id).where(CashEvent.business_id == b.business_id, CashEvent.source_type == p.source_type,
                                                           CashEvent.source_id == p.source_id, CashEvent.due_date == p.original_date,
                                                           CashEvent.amount == p.original_amount).limit(1))
    if still is None:
        raise PlanConflict("대응안을 만든 뒤 일정이 바뀌어 이 안을 적용할 수 없어요. 대응안을 다시 요청하세요.")
    now = datetime.now()
    p.status, p.decided_at = PlanStatus.APPROVED, now
    s.execute(update(ResponsePlan).where(ResponsePlan.run_id == p.run_id, ResponsePlan.plan_id != p.plan_id,
                                         ResponsePlan.status == PlanStatus.PROPOSED).values(status=PlanStatus.DECLINED, decided_at=now))
    s.flush()
    schedule_service.regenerate_source(s, b, p.source_type, p.source_id)
    return forecast_service.run(s, b)


def cancel(s: Session, b: Business, p: ResponsePlan) -> ForecastRun:
    if p.status != PlanStatus.APPROVED:
        raise PlanConflict("승인한 대응안만 되돌릴 수 있어요.")
    p.status, p.decided_at = PlanStatus.CANCELLED, datetime.now()
    s.flush()
    schedule_service.regenerate_source(s, b, p.source_type, p.source_id)
    return forecast_service.run(s, b)


def approved(s: Session, b: Business) -> list[dict]:
    return [_dto(p) for p in sorted(schedule_service.approved_plans(s, b.business_id), key=lambda p: p.plan_id)]
