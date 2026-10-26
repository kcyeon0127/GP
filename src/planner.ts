// S2 Retrieval Planner 파일럿: 자연어 질문 → 충격(Shock) 계획 JSON.
// LLM 엔드포인트가 있으면 LLM이 계획하고, 없으면 규칙 기반 파서가 같은 스키마를 만든다.
// 어느 쪽이든 validateShocks를 통과한 계획만 엔진에 들어간다(모델이 만든 값은 신뢰하지 않는다).
import { partners } from './data.ts'
import { callLLM } from './llm.ts'
import type { Shock } from './engine.ts'

export interface Plan {
  shocks: Shock[]
  source: 'llm' | 'rule'
  rationale: string
  confidence: number
  recognized: string[] // 질문에서 알아본 대상
  problems: string[] // 해석하지 못한 부분
}

const MAX_DAYS = 28

function parseDays(t: string): number | null {
  const words: [RegExp, number][] = [[/일주일|1주일/, 7], [/이주일|2주일/, 14], [/삼주일|3주일/, 21], [/한\s?달|1\s?개월|한\s?달간/, 28], [/두\s?달|2\s?개월/, 28]]
  for (const [re, d] of words) if (re.test(t)) return d
  const m = t.match(/(\d+)\s*(일|주|개월|달)/)
  if (!m) return null
  const n = +m[1]
  const d = m[2] === '일' ? n : m[2] === '주' ? n * 7 : n * 30
  return Math.min(d, MAX_DAYS)
}

function parseWon(t: string): number | null {
  const m = t.match(/(\d+(?:\.\d+)?)\s*(억|천만|백만|만)\s*원?/)
  if (!m) return null
  const unit = { 억: 1e8, 천만: 1e7, 백만: 1e6, 만: 1e4 }[m[2] as '억' | '천만' | '백만' | '만']
  return Math.round(+m[1] * unit)
}

function findPartner(t: string) {
  return partners.find((p) => t.includes(p.name) || t.includes(p.name.slice(0, 2)))
}

function ruleBasedPlan(text: string): Plan {
  const t = text.replace(/\s+/g, ' ').trim()
  const shocks: Shock[] = []
  const recognized: string[] = []
  const problems: string[] = []
  const partner = findPartner(t)
  if (partner) recognized.push(`거래처: ${partner.name}`)

  if (partner && /폐업|부도|망했|거래.*끊/.test(t)) {
    shocks.push({ type: 'partner_closure', partnerId: partner.id })
  } else if (/밀리|밀려|늦|지연|연체|안\s?들어/.test(t)) {
    if (partner) {
      const days = parseDays(t) ?? 14
      shocks.push({ type: 'settlement_delay', partnerId: partner.id, days })
      recognized.push(`지연: ${days}일`)
    } else problems.push('어느 거래처의 정산인지 알 수 없습니다.')
  }

  const rev = t.match(/매출[^.%\d]*?(\d+)\s*(%|퍼센트)/)
  if (rev || /매출.*(줄|감소|하락|떨어)/.test(t)) {
    const pct = rev ? +rev[1] : 20
    shocks.push({ type: 'revenue_drop', pct })
    recognized.push(`매출 감소: ${pct}%`)
  }

  const rate = t.match(/금리[^.%\d]*?(\d+(?:\.\d+)?)\s*(%p|%|퍼센트|bp)/i)
  if (rate || /금리.*(오르|올라|인상|상승)/.test(t)) {
    const bp = rate ? (rate[2].toLowerCase() === 'bp' ? +rate[1] : Math.round(+rate[1] * 100)) : 100
    shocks.push({ type: 'rate_up', bp })
    recognized.push(`금리 상승: +${(bp / 100).toFixed(1)}%p`)
  }

  if (/대출/.test(t) && /(받|신청|빌리|추가|늘)/.test(t)) {
    const amount = parseWon(t) ?? 5_000_000
    const months = (() => {
      const m = t.match(/(\d+)\s*(개월|년)/)
      return m ? (m[2] === '년' ? +m[1] * 12 : +m[1]) : 12
    })()
    shocks.push({ type: 'new_loan', amount, ratePct: 3.0, months })
    recognized.push(`신규 대출: ${(amount / 10000).toLocaleString('ko-KR')}만원, ${months}개월`)
  }

  if (shocks.length === 0 && problems.length === 0) problems.push('시뮬레이션할 상황(정산 지연, 매출 변화, 금리, 대출 등)을 찾지 못했습니다.')
  return {
    shocks,
    source: 'rule',
    rationale: '규칙 기반 해석기로 질문에서 거래처·기간·금액을 추출했습니다.',
    confidence: shocks.length ? (problems.length ? 0.5 : 0.8) : 0,
    recognized,
    problems,
  }
}

export function validateShocks(input: unknown): Shock[] | null {
  if (!Array.isArray(input) || input.length === 0 || input.length > 4) return null
  const ids = new Set(partners.map((p) => p.id))
  const out: Shock[] = []
  for (const k of input as Record<string, unknown>[]) {
    const num = (v: unknown, lo: number, hi: number) => typeof v === 'number' && Number.isFinite(v) && v >= lo && v <= hi
    switch (k.type) {
      case 'settlement_delay':
        if (!ids.has(k.partnerId as string) || !num(k.days, 1, MAX_DAYS)) return null
        out.push({ type: 'settlement_delay', partnerId: k.partnerId as string, days: k.days as number })
        break
      case 'partner_closure':
        if (!ids.has(k.partnerId as string)) return null
        out.push({ type: 'partner_closure', partnerId: k.partnerId as string })
        break
      case 'revenue_drop':
        if (!num(k.pct, 1, 90)) return null
        out.push({ type: 'revenue_drop', pct: k.pct as number })
        break
      case 'rate_up':
        if (!num(k.bp, 10, 1000)) return null
        out.push({ type: 'rate_up', bp: k.bp as number })
        break
      case 'new_loan':
        if (!num(k.amount, 100_000, 1_000_000_000) || !num(k.ratePct, 0, 30) || !num(k.months, 1, 120)) return null
        out.push({ type: 'new_loan', amount: k.amount as number, ratePct: k.ratePct as number, months: k.months as number })
        break
      default:
        return null
    }
  }
  return out
}

export async function planQuery(text: string): Promise<Plan> {
  const llm = await callLLM<{ shocks: unknown; rationale?: string; confidence?: number }>('plan', {
    query: text,
    entities: { partners: partners.map((p) => ({ id: p.id, name: p.name, role: p.role })) },
  })
  const checked = llm ? validateShocks(llm.shocks) : null
  if (llm && checked) {
    return { shocks: checked, source: 'llm', rationale: llm.rationale ?? '', confidence: llm.confidence ?? 0.7, recognized: [], problems: [] }
  }
  return ruleBasedPlan(text) // LLM 없음·실패·스키마 위반 시 대체 경로
}

export function describeShock(k: Shock): string {
  const name = (id: string) => partners.find((p) => p.id === id)?.name ?? id
  switch (k.type) {
    case 'settlement_delay': return `${name(k.partnerId)} 정산 ${k.days}일 지연`
    case 'partner_closure': return `${name(k.partnerId)} 폐업`
    case 'revenue_drop': return `매출 ${k.pct}% 감소`
    case 'rate_up': return `변동금리 +${(k.bp / 100).toFixed(1)}%p`
    case 'new_loan': return `신규 대출 ${(k.amount / 10000).toLocaleString('ko-KR')}만원(연 ${k.ratePct}%, ${k.months}개월)`
    default: return k.type
  }
}
