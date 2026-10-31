import os

# API·그래프 테스트는 개발 DB와 분리한다: PostgreSQL gp_test DB, Neo4j는 사업장 999번 노드만 쓴다.
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://gp:gp@localhost:5432/gp_test")
os.environ.setdefault("BUSINESS_ID", "999")
