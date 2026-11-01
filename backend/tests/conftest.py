import os

# API·그래프 테스트는 개발 DB와 분리한다: PostgreSQL gp_test DB, Neo4j는 사업장 999번 노드만 쓴다.
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://gp:gp@localhost:5432/gp_test")
os.environ.setdefault("BUSINESS_ID", "999")

import pytest  # noqa: E402


@pytest.fixture(scope="module")
def client():
    """빈 gp_test DB로 시작하는 API 클라이언트. 기준일 11/1, 현재 잔액·안전 잔액 100만 원."""
    from fastapi.testclient import TestClient

    from app import models  # noqa: F401
    from app.db import Base, engine
    from app.main import app

    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    # Neo4j는 개발 DB와 같이 쓰므로, 테스트 행의 ID가 개발 데이터 ID와 겹치지 않게 시퀀스를 띄운다
    with engine.begin() as conn:
        for (seq,) in conn.exec_driver_sql("SELECT sequence_name FROM information_schema.sequences"):
            conn.exec_driver_sql(f"ALTER SEQUENCE {seq} RESTART WITH 1000000")
    with TestClient(app) as c:
        c.post("/api/forecasts", json={"base_date": "2026-11-01", "current_balance": 1_000_000, "safety_balance": 1_000_000})
        yield c
