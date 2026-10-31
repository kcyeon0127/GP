"""DocumentRepository: pgvector 문서 조각 저장·검색."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Document, DocumentChunk


def search(s: Session, business_id: int, vector: list[float], limit: int = 5, contract_ids: list[int] | None = None) -> list[tuple[DocumentChunk, Document, float]]:
    """코사인 유사도 순 (1 - cosine distance)."""
    score = (1 - DocumentChunk.embedding.cosine_distance(vector)).label("score")
    q = select(DocumentChunk, Document, score).join(Document).where(Document.business_id == business_id)
    if contract_ids is not None:
        q = q.where(DocumentChunk.contract_id.in_(contract_ids))
    return [(c, d, float(sc)) for c, d, sc in s.execute(q.order_by(score.desc()).limit(limit))]
