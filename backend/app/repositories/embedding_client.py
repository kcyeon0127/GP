"""임베딩 어댑터: OpenAI 호환 /v1/embeddings (lab 서버 vLLM bge-m3). 판단 없이 호출만 한다."""
import httpx

from ..config import EMBEDDING_API_KEY, EMBEDDING_MODEL, EMBEDDING_URL


def embed(texts: list[str]) -> list[list[float]]:
    r = httpx.post(f"{EMBEDDING_URL}/embeddings", json={"model": EMBEDDING_MODEL, "input": texts},
                   headers={"Authorization": f"Bearer {EMBEDDING_API_KEY}"}, timeout=60)
    r.raise_for_status()
    return [d["embedding"] for d in sorted(r.json()["data"], key=lambda d: d["index"])]
