"""생성형 sLLM 어댑터: OpenAI 호환 /v1/chat/completions (lab 서버 vLLM). 판단 없이 호출만 한다.

실패하면 예외만 던진다. 템플릿으로 대체할지는 서비스가 정한다.
- LLMUnavailable: 서버에 닿지 않음 (터널 끊김·타임아웃·5xx)
- LLMError: 닿았지만 응답 모양이 이상함
"""
import httpx

from ..config import LLM_API_KEY, LLM_MODEL, LLM_TIMEOUT, LLM_URL


class LLMError(Exception):
    pass


class LLMUnavailable(LLMError):
    pass


def chat(messages: list[dict], *, max_tokens: int = 400, temperature: float = 0.1, json_mode: bool = False) -> str:
    body = {"model": LLM_MODEL, "messages": messages, "max_tokens": max_tokens, "temperature": temperature}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    try:
        r = httpx.post(f"{LLM_URL}/chat/completions", json=body, headers={"Authorization": f"Bearer {LLM_API_KEY}"}, timeout=LLM_TIMEOUT)
        r.raise_for_status()
    except (httpx.TransportError, httpx.HTTPStatusError) as e:
        raise LLMUnavailable(type(e).__name__) from e
    try:
        content = r.json()["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as e:
        raise LLMError("응답 형식 오류") from e
    if not isinstance(content, str) or not content.strip():
        raise LLMError("빈 응답")
    return content
