"""상생여지도 백엔드 (FastAPI). 실행: uvicorn app.main:app --reload"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from .api import counterparties, fixed_costs_loans, forecasts
from .config import CORS_ORIGINS
from .db import init_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="상생여지도 API", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError):
    """빠진 칸·잘못된 칸 이름을 fields로 돌려준다 (US-01 AC-02, US-02 AC-03)."""
    fields = sorted({str(e["loc"][-1]) for e in exc.errors() if len(e["loc"]) > 1})
    errors = [{"field": str(e["loc"][-1]), "msg": e["msg"]} for e in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": "필수 항목을 확인하세요", "fields": fields, "errors": errors})


@app.exception_handler(IntegrityError)
async def integrity_error(_: Request, exc: IntegrityError):
    if "uq_counterparty_business_name" in str(exc.orig):
        return JSONResponse(status_code=409, content={"detail": "이미 등록된 거래처 이름입니다"})
    return JSONResponse(status_code=422, content={"detail": "저장할 수 없는 값입니다", "error": str(exc.orig).splitlines()[0]})


for module in (counterparties, fixed_costs_loans, forecasts):
    app.include_router(module.router)


@app.get("/api/health")
def health():
    return {"ok": True}
