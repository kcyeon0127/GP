// M4 Forecast + M5 Scenario Engine 파일럿(클라이언트 구현). 숫자는 전부 여기서 계산한다.
import { baseEvents, business, type CashEvent } from './data.ts'

export const HORIZON = 28
const RUNS = 600

export type Shock =
  | { type: 'settlement_delay'; partnerId: string; days: number }
  | { type: 'revenue_drop'; pct: number }
  | { type: 'rate_up'; bp: number }
  | { type: 'partner_closure'; partnerId: string }
  | { type: 'payable_defer'; eventId: string; days: number }
  | { type: 'payable_cut'; pct: number }
  | { type: 'cost_shift'; eventId: string; days: number }
  | { type: 'new_loan'; amount: number; ratePct: number; months: number }

export interface ModelState {
  events: CashEvent[]
  salesFactor: number
}

export interface Forecast {
  p10: number[] // index 0 = 오늘 시작 잔액, 1..28 = 각 일 종료 잔액
  p50: number[]
  p90: number[]
  shortProb: number[] // 일별 잔액 < 최소잔액 확률
  minP50: number
  minDay: number
  firstShortDay: number | null // P50 기준 첫 부족일
  eventRisk: Record<string, number> // 지출 이벤트 당일 직후 잔액 부족 확률
}

export type Signal = 'green' | 'yellow' | 'red'

function mulberry32(seed: number) {
  let a = seed
  return () => {
    a |= 0
    a = (a + 0x6d2b79f5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

function gauss(r: () => number) {
  const u = Math.max(r(), 1e-9)
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * r())
}

const q = (sorted: number[], p: number) => sorted[Math.min(sorted.length - 1, Math.floor(p * sorted.length))]

export function initialState(): ModelState {
  return { events: baseEvents.map((e) => ({ ...e, delay: e.delay && { ...e.delay } })), salesFactor: 1 }
}

export function applyShocks(shocks: Shock[], from: ModelState = initialState()): ModelState {
  const s: ModelState = { events: from.events.map((e) => ({ ...e, delay: e.delay && { ...e.delay } })), salesFactor: from.salesFactor }
  for (const k of shocks) {
    switch (k.type) {
      case 'settlement_delay':
        s.events.forEach((e) => {
          if (e.kind === 'settlement' && e.partnerId === k.partnerId) e.day += k.days
        })
        break
      case 'revenue_drop':
        s.salesFactor *= 1 - k.pct / 100
        s.events.forEach((e) => {
          if (e.kind === 'settlement') e.amount = Math.round(e.amount * (1 - k.pct / 100))
        })
        break
      case 'rate_up':
        s.events.forEach((e) => {
          if (e.floatingRate && e.loanId) {
            const bal = business.loanBalances[e.loanId] ?? 0
            e.amount += Math.round((bal * (k.bp / 10000)) / 12)
          }
        })
        break
      case 'partner_closure':
        s.events = s.events.filter((e) => !(e.kind === 'settlement' && e.partnerId === k.partnerId))
        break
      case 'payable_defer':
      case 'cost_shift':
        s.events.forEach((e) => {
          if (e.id === k.eventId) e.day += k.days
        })
        break
      case 'payable_cut':
        s.events.forEach((e) => {
          if (e.kind === 'payable') e.amount = Math.round(e.amount * (1 - k.pct / 100))
        })
        break
      case 'new_loan': {
        const monthly = Math.round(k.amount / k.months + (k.amount * (k.ratePct / 100)) / 12)
        s.events.push({ id: 'NL-in', label: '신규 대출 입금', kind: 'loan', day: 3, amount: k.amount, direction: 'in' })
        s.events.push({ id: 'NL-out', label: '신규 대출 상환', kind: 'loan', day: 26, amount: monthly, direction: 'out', loanId: 'NEW' })
        break
      }
    }
  }
  return s
}

export function forecast(state: ModelState, seed = 7): Forecast {
  const rand = mulberry32(seed)
  const perDay: number[][] = Array.from({ length: HORIZON + 1 }, () => [])
  const riskHits: Record<string, number> = {}
  const sales = business.salesPerDay * state.salesFactor

  for (let run = 0; run < RUNS; run++) {
    const delta = new Array(HORIZON + 2).fill(0)
    const outs: { id: string; day: number }[] = []
    for (const e of state.events) {
      let day = e.day
      if (e.delay) day += Math.max(0, Math.round(e.delay.mean + gauss(rand) * e.delay.sd))
      if (day < 1) day = 1
      if (day > HORIZON) continue
      delta[day] += e.direction === 'in' ? e.amount : -e.amount
      if (e.direction === 'out') outs.push({ id: e.id, day })
    }
    let bal = business.startBalance
    const track: number[] = [bal]
    for (let d = 1; d <= HORIZON; d++) {
      const weekday = ((d + 3) % 7) < 5 // 2026-10-01은 목요일
      bal += delta[d] + (weekday ? sales * 1.4 : sales * 0.2)
      track.push(bal)
      perDay[d].push(bal)
    }
    perDay[0].push(business.startBalance)
    for (const o of outs) if (track[o.day] < business.minBalance) riskHits[o.id] = (riskHits[o.id] ?? 0) + 1
  }

  const p10: number[] = []
  const p50: number[] = []
  const p90: number[] = []
  const shortProb: number[] = []
  for (let d = 0; d <= HORIZON; d++) {
    const s = [...perDay[d]].sort((a, b) => a - b)
    p10.push(q(s, 0.1))
    p50.push(q(s, 0.5))
    p90.push(q(s, 0.9))
    shortProb.push(s.filter((v) => v < business.minBalance).length / s.length)
  }
  let minP50 = Infinity
  let minDay = 0
  let firstShortDay: number | null = null
  for (let d = 1; d <= HORIZON; d++) {
    if (p50[d] < minP50) {
      minP50 = p50[d]
      minDay = d
    }
    if (firstShortDay === null && p50[d] < business.minBalance) firstShortDay = d
  }
  const eventRisk: Record<string, number> = {}
  for (const k of Object.keys(riskHits)) eventRisk[k] = riskHits[k] / RUNS
  return { p10, p50, p90, shortProb, minP50, minDay, firstShortDay, eventRisk }
}

// M6 조기경보 규칙
export function signalOf(f: Forecast): { level: Signal; reason: string } {
  const red = f.p50.findIndex((v, d) => d >= 1 && d <= 14 && v < business.minBalance)
  if (red > 0) return { level: 'red', reason: `${red}일 뒤 잔액이 최소 유지 잔액 아래로 내려갑니다.` }
  const yellow = f.p10.findIndex((v, d) => d >= 1 && d <= 28 && v < business.minBalance)
  if (yellow > 0) return { level: 'yellow', reason: `${yellow}일 뒤 상황이 나빠지면 잔액이 부족해질 수 있습니다.` }
  return { level: 'green', reason: '28일 안에 잔액 부족 신호가 없습니다.' }
}

export interface Diff {
  minP50Delta: number
  firstShortBefore: number | null
  firstShortAfter: number | null
  newlyRisky: { id: string; label: string; before: number; after: number }[]
}

export function compare(base: Forecast, next: Forecast, events: CashEvent[]): Diff {
  const newlyRisky = events
    .filter((e) => e.direction === 'out')
    .map((e) => ({ id: e.id, label: e.label, before: base.eventRisk[e.id] ?? 0, after: next.eventRisk[e.id] ?? 0 }))
    .filter((r) => r.after - r.before >= 0.1)
    .sort((a, b) => b.after - a.after)
  return {
    minP50Delta: next.minP50 - base.minP50,
    firstShortBefore: base.firstShortDay,
    firstShortAfter: next.firstShortDay,
    newlyRisky,
  }
}

// 충격이 전파되는 경로(그래프 강조용): 충격 대상 → 정산 → 계좌 → 위험해진 지급
export function impactedNodeIds(shocks: Shock[], risky: string[]): Set<string> {
  const ids = new Set<string>()
  for (const k of shocks) {
    if ('partnerId' in k) {
      ids.add(k.partnerId)
      baseEvents.filter((e) => e.kind === 'settlement' && e.partnerId === k.partnerId).forEach((e) => ids.add(e.id))
    }
    if (k.type === 'revenue_drop') baseEvents.filter((e) => e.kind === 'settlement').forEach((e) => ids.add(e.id))
    if (k.type === 'rate_up') baseEvents.filter((e) => e.floatingRate).forEach((e) => ids.add(e.id))
  }
  if (ids.size || risky.length) ids.add('ACC')
  risky.forEach((r) => ids.add(r))
  return ids
}

export const base = (() => {
  const st = initialState()
  return { state: st, forecast: forecast(st) }
})()
