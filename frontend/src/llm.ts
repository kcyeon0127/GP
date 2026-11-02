// LLM 연결 지점. VITE_LLM_ENDPOINT(FastAPI 등)가 설정되어 있으면 그쪽을 호출하고,
// 없거나 실패하면 null을 돌려줘서 호출부가 규칙 기반 대체 경로(fallback)를 쓴다.
// 서버 계약:
//   POST {endpoint}/plan     { query, entities }            -> { shocks: Shock[], rationale: string, confidence: number }
//   POST {endpoint}/explain  { query, evidence, result }    -> { text: string }
// API 키는 서버에만 둔다. 브라우저 번들에 넣지 않는다.

const ENDPOINT: string | undefined = import.meta.env?.VITE_LLM_ENDPOINT

export const llmEnabled = Boolean(ENDPOINT)

export async function callLLM<T>(path: 'plan' | 'explain', body: unknown): Promise<T | null> {
  if (!ENDPOINT) return null
  try {
    const res = await fetch(`${ENDPOINT.replace(/\/$/, '')}/${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(20_000),
    })
    if (!res.ok) return null
    return (await res.json()) as T
  } catch {
    return null
  }
}
