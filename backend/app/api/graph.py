"""US-06: 금융지도 그래프 동기화(T20)와 조회(T21)."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import Business
from ..services import graph_service
from .deps import business

router = APIRouter(prefix="/api")


@router.post("/graph/sync")
def sync_graph(s: Session = Depends(get_session), b: Business = Depends(business)):
    out = graph_service.sync(s, b)
    s.commit()
    return out


@router.get("/graph")
def get_graph(include_events: bool = False, b: Business = Depends(business)):
    return graph_service.graph_json(b, include_events)
