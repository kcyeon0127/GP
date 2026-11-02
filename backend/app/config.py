"""환경 설정. backend/.env 또는 환경변수로 덮어쓴다."""
import os

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://gp:gp@localhost:5432/gp")
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "gp-password")
# 임베딩: OpenAI 호환 /v1/embeddings (lab 서버 vLLM bge-m3, SSH 터널로 localhost:8101)
EMBEDDING_URL = os.getenv("EMBEDDING_URL", "http://localhost:8101/v1")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "bge-m3")
EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY", "")
EMBEDDING_DIM = 1024
# 근거 검색에서 문서 조각을 근거로 인정하는 최소 유사도 (T23 Spike 잠정값)
EVIDENCE_MIN_SCORE = float(os.getenv("EVIDENCE_MIN_SCORE", "0.55"))
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:5191").split(",")
