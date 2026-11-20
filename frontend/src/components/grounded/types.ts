// US-18 근거기반 AI 응답 타입 (backend explain_service · confidence_service와 같은 모양)
export type ConfLevel = 'HIGH' | 'MEDIUM' | 'LOW'
export interface ConfidenceDto {
  level: ConfLevel; score: number; reasons: string[]; missing: string[]
  factors: { key: string; points: number; weight: number }[]
}
export interface ExplanationDto {
  text: string; source: 'llm' | 'template'; verified: boolean; cited_ids: string[]
  fallback_reason: 'LLM_DOWN' | 'LLM_ERROR' | 'VERIFY_FAILED' | 'HOLD' | null; fallback_ko: string | null
  problems: string[]; calc: { id: string; text: string } | null
}
export interface GroundedEvidence { id: string; type: string; text: string | null }

/** [P1] 칩을 누르면 같은 화면(scope)의 근거 행을 찾아 잠깐 강조한다. 행 id는 `ev-${scope}-${id}`. */
export function highlight(scope: string, id: string) {
  const el = document.getElementById(`ev-${scope}-${id}`)
  if (!el) return
  el.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  el.classList.remove('ev-hit')
  void el.offsetWidth // 같은 칩을 연달아 눌러도 다시 강조되게
  el.classList.add('ev-hit')
  window.setTimeout(() => el.classList.remove('ev-hit'), 1800)
}
