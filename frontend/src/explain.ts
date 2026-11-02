// 결과 설명(LLM 추론 자리) + M9 응답 검증.
// LLM이 있으면 근거와 계산 결과를 주고 문장을 받는다. 근거에 없는 숫자나 존재하지 않는 근거 ID가 있으면 버리고,
// 같은 근거로 만든 템플릿 문장으로 대체한다. 계산(숫자)은 항상 엔진이 한다.
import { callLLM } from './llm.ts'
import { dayLabel, won } from './data.ts'
import type { Diff, Forecast, Signal } from './engine.ts'
import type { Evidence } from './graphrag.ts'
import { describeShock } from './planner.ts'
import type { Shock } from './engine.ts'

export interface Explanation {
  text: string
  source: 'llm' | 'template'
  verified: boolean
  note?: string
}

const SIGNAL_KO: Record<Signal, string> = { green: '안정', yellow: '주의', red: '위험' }

export function resultEvidence(start: number, shocks: Shock[], base: Forecast, next: Forecast, diff: Diff, level: Signal): Evidence[] {
  const out: Evidence[] = []
  const id = (i: number) => `E${start + i}`
  out.push({
    id: id(0),
    kind: 'result',
    nodes: [],
    text: `가정(${shocks.map(describeShock).join(', ')})을 적용하면 4주 동안의 예상 최저 잔액은${won(base.minP50)} → ${won(next.minP50)}(변화 ${won(diff.minP50Delta)})이고, 자금 상태는 ${SIGNAL_KO[level]}입니다.`,
  })
  out.push({
    id: id(1),
    kind: 'result',
    nodes: [],
    text: diff.firstShortAfter
      ? `첫 부족 예상일은 ${dayLabel(diff.firstShortAfter)}입니다.`
      : '4주 안에 잔액이 0원 아래로 내려가는 날은 없습니다.',
  })
  if (diff.newlyRisky.length) {
    out.push({
      id: id(2),
      kind: 'result',
      nodes: diff.newlyRisky.map((r) => r.id),
      text: `위험이 늘어난 지급: ${diff.newlyRisky.map((r) => `${r.label}(부족 확률 ${Math.round(r.before * 100)}%에서 ${Math.round(r.after * 100)}%)`).join(', ')}.`,
    })
  }
  return out
}

const numTokens = (s: string) => (s.match(/\d[\d,.]*/g) ?? []).map((n) => n.replace(/[,.]+$/g, '').replace(/,/g, ''))

// M9: 숫자와 근거 ID 대조
export function verify(text: string, evidence: Evidence[]): { ok: boolean; reason?: string } {
  const allowed = new Set(evidence.flatMap((e) => numTokens(e.text)))
  evidence.forEach((e) => numTokens(e.id).forEach((n) => allowed.add(n)))
  const ids = new Set(evidence.map((e) => e.id))
  for (const ref of text.match(/E\d+/g) ?? []) if (!ids.has(ref)) return { ok: false, reason: `존재하지 않는 근거 ${ref}` }
  const stripped = text.replace(/E\d+/g, '')
  for (const n of numTokens(stripped)) if (!allowed.has(n)) return { ok: false, reason: `근거에 없는 숫자 ${n}` }
  if (/(반드시|무조건).{0,10}(대출|받으세요|신청하세요)/.test(text)) return { ok: false, reason: '단정형 금융 권유 표현' }
  return { ok: true }
}

function template(evidence: Evidence[]): string {
  const res = evidence.filter((e) => e.kind === 'result')
  const ctx = evidence.filter((e) => e.kind !== 'result')
  const ctxRefs = ctx.slice(0, 4).map((e) => `[${e.id}]`).join('')
  return `${res.map((e) => `${e.text} [${e.id}]`).join(' ')}\n이 판단에는 현재 상황 ${ctxRefs} 정보를 사용했습니다.`
}

export async function explain(query: string, evidence: Evidence[]): Promise<Explanation> {
  const llm = await callLLM<{ text: string }>('explain', { query, evidence })
  if (llm?.text) {
    const v = verify(llm.text, evidence)
    if (v.ok) return { text: llm.text, source: 'llm', verified: true }
    return { text: template(evidence), source: 'template', verified: true, note: `LLM 답변을 검증에서 거절했습니다(${v.reason}). 계산 결과 템플릿으로 대체했습니다.` }
  }
  return { text: template(evidence), source: 'template', verified: true }
}
