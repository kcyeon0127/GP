"""US-18 D: 말로 물어보기 (/simulation/ask). 질문을 What-if 조건으로 바꿔 계산하고 근거 인용 설명과 신뢰도를 붙인다."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import Business
from ..services import ask_service
from .deps import business

router = APIRouter(prefix="/api")


class AskIn(BaseModel):
    query: str = Field(min_length=1, max_length=300, description="사장님 질문")


@router.post("/ask")
def ask(body: AskIn, s: Session = Depends(get_session), b: Business = Depends(business)):
    out = ask_service.ask(s, b, body.query.strip())
    s.commit()
    return out
