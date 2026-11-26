"""ConfidenceService (US-18): 경보와 질문 결과가 얼마나 근거에 기대고 있는지 등급을 매긴다.

요인 (배점은 domain.constants):
- 경로: 영향 일정 중 금융지도 경로(P 근거)가 있는 비율
- 조항: 영향 일정의 계약 중 계약 문서 조항(D 근거)이 있는 비율 (질문 화면은 질문 해석 완전성으로 바꾼다)
- 연결: 영향 일정 중 받는 곳·계약이 등록된 비율
- 정산: 경보일 뒤 들어올 정산 일정이 등록되어 있는지
거래내역 기간·정산 이력은 아직 DB에 저장하지 않아 요인에 넣지 않았다 (불러오기는 후보만 만든다).
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain import confidence as cf
from ..domain.constants import CONF_W_CLAUSE, CONF_W_INFLOW, CONF_W_LINK, CONF_W_PATH, HORIZON_DAYS
from ..domain.enums import CashDirection, CashSource
from ..models import CashEvent, Contract, Document, DocumentChunk, FixedCost, ForecastRun, Loan
from . import forecast_service

NEED_SALES = "매출처의 정산 일정(거래처·결제 조건)을 등록하세요."
GRAPH_DOWN = "금융지도 서버를 켠 뒤 다시 확인하세요."
DOCS_DOWN = "계약 문서 검색 서버(임베딩)를 연결한 뒤 다시 확인하세요."


def contract_of(s: Session, e: CashEvent) -> int | None:
    if e.source_type == CashSource.CONTRACT:
        return e.source_id
    obj = s.get(FixedCost if e.source_type == CashSource.FIXED_COST else Loan, e.source_id)
    return obj.contract_id if obj else None


def _unique_sources(events: list[CashEvent]) -> list[CashEvent]:
    """매달 같은 지급이 여러 번 나와도 출처 하나로 센다."""
    seen, out = set(), []
    for e in events:
        if (e.source_type, e.source_id) not in seen:
            seen.add((e.source_type, e.source_id))
            out.append(e)
    return out


def _path_factor(events: list[CashEvent], evidence: list[dict], graph_down: bool) -> cf.Factor:
    refs = {ev["ref"] for ev in evidence if ev["type"] == "GRAPH_PATH"}
    have = sum(f"event:{e.cash_event_id}" in refs for e in events)
    reason = "금융지도 서버에 연결되지 않아 경로를 확인하지 못했어요." if graph_down else f"영향 일정 {len(events)}건 중 {have}건을 거래관계 경로로 확인했어요."
    return cf.Factor("path", cf.ratio(have, len(events)), CONF_W_PATH, reason, [GRAPH_DOWN] if graph_down else [])


def _clause_factor(s: Session, business_id: int, events: list[CashEvent], evidence: list[dict], docs_down: bool) -> cf.Factor:
    keys = [ev["ref"] for ev in evidence if ev["type"] == "DOCUMENT_CHUNK"]
    with_clause = set(s.scalars(select(DocumentChunk.contract_id).where(DocumentChunk.key.in_(keys)))) if keys else set()
    contracts = list(dict.fromkeys(c for e in _unique_sources(events) if (c := contract_of(s, e)) is not None))
    have = [c for c in contracts if c in with_clause]
    missing: list[str] = []
    if docs_down:
        missing.append(DOCS_DOWN)
    else:
        for cid in contracts:
            if cid in with_clause:
                continue
            c = s.get(Contract, cid)
            party = c.counterparty.name if c and c.counterparty else "거래처"
            doc = s.scalar(select(Document).where(Document.business_id == business_id, Document.contract_id == cid).limit(1))
            missing.append(f"'{party}' 계약서를 등록하세요." if doc is None else f"'{doc.title}'의 지급 조건 조항을 확인하세요.")
    if docs_down:
        reason = "계약 문서 검색 서버에 연결되지 않아 조항을 확인하지 못했어요."
    elif not contracts:
        reason = "영향 일정에 연결된 계약이 없어 조항을 찾을 수 없어요."
    else:
        reason = f"관련 계약 {len(contracts)}건 중 {len(have)}건에서 지급 조건 조항을 찾았어요."
    return cf.Factor("clause", cf.ratio(len(have), len(contracts)), CONF_W_CLAUSE, reason, missing[:3])


def _link_factor(s: Session, events: list[CashEvent]) -> cf.Factor:
    srcs = _unique_sources(events)
    unlinked = [e for e in srcs if contract_of(s, e) is None]
    have = len(srcs) - len(unlinked)
    return cf.Factor("link", cf.ratio(have, len(srcs)), CONF_W_LINK, f"영향 일정 {len(srcs)}곳 중 {have}곳의 계약이 등록돼 있어요.",
                     [f"'{e.label}'의 받는 곳 계약을 등록하세요." for e in unlinked[:3]])


def _inflow_factor(s: Session, business_id: int, base_date, after) -> cf.Factor:
    end = base_date.toordinal() + HORIZON_DAYS - 1
    has = any(e.direction == CashDirection.IN and (after is None or after < e.due_date) and e.due_date.toordinal() <= end
              for e in forecast_service.events_of(s, business_id))
    return cf.Factor("inflow", 1.0 if has else 0.0, CONF_W_INFLOW,
                     "경보일 뒤 들어올 정산 일정이 등록돼 있어요." if has else "경보일 뒤 들어올 정산 일정이 없어요.", [] if has else [NEED_SALES])


def for_alert(s: Session, r: ForecastRun, evidence: list[dict], graph_down: bool = False, docs_down: bool = False) -> dict | None:
    """경보 신뢰도. 경보가 없으면(안전) None."""
    events = [e for e, _ in forecast_service.drivers(s, r)]
    if not events:
        return None
    factors = [_path_factor(events, evidence, graph_down), _clause_factor(s, r.business_id, events, evidence, docs_down),
               _link_factor(s, events), _inflow_factor(s, r.business_id, r.base_date, forecast_service.trigger_date(r))]
    return cf.assess(factors, cap_medium=graph_down or docs_down)


def for_question(s: Session, b, event_ids: list[int], evidence: list[dict], parse_ratio: float, parse_reason: str,
                 parse_missing: list[str], graph_down: bool = False) -> dict:
    """질문 결과 신뢰도: 조항 대신 질문 해석이 얼마나 완전했는지를 본다."""
    events = list(s.scalars(select(CashEvent).where(CashEvent.cash_event_id.in_(event_ids)))) if event_ids else []
    factors = [_path_factor(events, evidence, graph_down) if events else cf.Factor("path", 0.0, CONF_W_PATH, "조건으로 바뀌는 일정이 없어요."),
               cf.Factor("parse", parse_ratio, CONF_W_CLAUSE, parse_reason, parse_missing),
               _link_factor(s, events) if events else cf.Factor("link", 0.0, CONF_W_LINK, "연결할 일정이 없어요."),
               _inflow_factor(s, b.business_id, b.base_date, None)]
    return cf.assess(factors, cap_medium=graph_down)
