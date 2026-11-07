"""US-07: 경보 원인 근거 조회 (T26)."""
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import Business, Document, DocumentChunk
from ..services import evidence_service
from .deps import business
from .forecasts import _run

router = APIRouter(prefix="/api")


@router.get("/alerts/{run_id}/evidence")
def alert_evidence(run_id: int, s: Session = Depends(get_session), b: Business = Depends(business)):
    r = _run(s, run_id, b)
    out = evidence_service.collect(s, r)
    s.commit()
    return out


@router.get("/documents/summary")
def documents_summary(s: Session = Depends(get_session), b: Business = Depends(business)):
    """홈 요약 지도의 "조항 N개" 표시용 건수."""
    docs = s.scalar(select(func.count()).select_from(Document).where(Document.business_id == b.business_id))
    chunks = s.scalar(select(func.count()).select_from(DocumentChunk).join(Document).where(Document.business_id == b.business_id))
    return {"documents": docs, "chunks": chunks}
