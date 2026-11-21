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
# 생성형 sLLM: OpenAI 호환 /v1/chat/completions (lab 서버 vLLM Qwen2.5-1.5B-Instruct, SSH 터널로 localhost:8100)
# 계약 원문이 섞인 근거를 보내므로 내부 서버만 쓴다. 외부 API 폴백은 두지 않는다.
LLM_URL = os.getenv("LLM_URL", "http://localhost:8100/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "Qwen2.5-1.5B-Instruct")
LLM_API_KEY = os.getenv("LLM_API_KEY", EMBEDDING_API_KEY)  # 같은 lab 서버 키를 쓴다
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "20"))
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:5191").split(",")
