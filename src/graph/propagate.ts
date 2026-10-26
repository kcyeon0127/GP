// 위험 전파 엔진(순수 함수). propagate(graph, shock) → 영향받은 노드·경로·효과·잔액 결과.
// 충격 노드에서 BFS로 최대 5홉까지 탐색하고, 엣지 타입별 handler가 전파 여부와 효과를 정한다.
// 현금 이벤트(날짜 이동·금액 변경)는 패치로 모아 기존 몬테카를로 엔진(engine.ts)에 그대로 넣어 일별 잔액을 계산한다.
import { baseEvents, isoDay, knownDelays, won } from '../data.ts'
import { base, compare, forecast, initialState, type Forecast, type ModelState } from '../engine.ts'
import type { CashEvent } from '../data.ts'
import type { EdgeType, FinanceGraph, GraphEdge, GraphNode } from '../data/financeGraph.ts'

export const MAX_HOPS = 5

export type GraphShock =
  | { type: 'settlement_delay'; partnerId: string; days: number } // 매출처면 정산 지연, 매입처면 대금 지급 지연
  | { type: 'loan_default'; loanId: string }
  | { type: 'payment_switch'; targetId: string; cardId: string; prevMonthSpend?: number }
  | { type: 'rate_up'; pp: number }
  | { type: 'revenue_drop'; pct: number } // 현장 매출과 모든 정산액이 pct% 줄어든다
  | { type: 'current' } // 이미 벌어진 상황(확정된 정산 지연 등)이 지금 어디까지 번지는지 본다. 현금 패치는 없다
  | { type: 'partner_closure'; partnerId: string }
  | { type: 'refinance'; loanId: string; productId: string }

export type Status = 'at_risk' | 'triggered' | 'improved' | 'changed'
const RANK: Record<Status, number> = { changed: 1, improved: 2, at_risk: 3, triggered: 4 }

export interface NodeEffect { nodeId: string; status: Status; hop: number; reason: string }
export type Patch =
  | { id: string; kind: 'shift'; days: number }
  | { id: string; kind: 'setDay'; day: number }
  | { id: string; kind: 'remove' }
  | { id: string; kind: 'amount'; factor?: number; delta?: number }
  | { kind: 'sales'; factor: number } // 일 평균 현장 매출 배율
  | { kind: 'add'; event: CashEvent }

export interface Repayment { id: string; label: string; date: string; amount: number; prob: number }
export interface PropagationResult {
  shock: GraphShock
  nodes: Map<string, NodeEffect>
  edges: Map<string, number> // 엣지 ID → 전파된 홉
  paths: string[][] // 충격 노드에서 말단까지의 노드 경로
  hops: number
  patches: Patch[]
  suggestions: { signalId: string; targetId: string; text: string }[]
  balance: {
    baseMinP50: number; minP50: number; minDay: number
    baseFirstShortDay: number | null; firstShortDay: number | null
    repayments: Repayment[] // 위험해진 상환
  }
  notes: string[] // 홉 순서의 설명
}

// ---------- 내부 상태 ----------
interface State {
  byId: Map<string, GraphNode>
  incident: Map<string, GraphEdge[]>
  graph: FinanceGraph
  shock: GraphShock
  status: Map<string, NodeEffect>
  patches: Patch[]
  partnerDelay: Map<string, number>
  payableDelay: Map<string, number>
  closed: Set<string>
  overdue: Set<string>
  paidWith: Map<string, string>
  cache: { n: number; risky: Map<string, number> } | null
}

interface Ctx { edge: GraphEdge; origin: 'source' | 'target'; from: GraphNode; to: GraphNode; s: State }
interface Effect { to?: { status: Status; reason: string }; patch?: Patch; enqueue?: boolean }
type Handler = (c: Ctx) => Effect | null

export function applyPatches(patches: Patch[]): ModelState {
  const st = initialState()
  for (const p of patches) {
    if (p.kind === 'add') { st.events.push({ ...p.event }); continue }
    if (p.kind === 'sales') { st.salesFactor *= p.factor; continue }
    if (p.kind === 'remove') { st.events = st.events.filter((e) => e.id !== p.id); continue }
    const e = st.events.find((x) => x.id === p.id)
    if (!e) continue
    if (p.kind === 'shift') e.day += p.days
    else if (p.kind === 'setDay') e.day = p.day
    else e.amount = Math.max(0, Math.round(e.amount * (p.factor ?? 1) + (p.delta ?? 0)))
  }
  return st
}

const evOf = (id: string) => baseEvents.find((e) => e.id === id)

function risky(s: State): Map<string, number> {
  // 현재 상황: 기준선 자체가 이미 위험하므로 "기준선 대비 증가"가 아니라 절대 확률로 판단한다
  if (s.shock.type === 'current') return new Map(Object.entries(base.forecast.eventRisk).filter(([, p]) => p >= 0.5))
  if (s.cache && s.cache.n === s.patches.length) return s.cache.risky
  const st = applyPatches(s.patches)
  const f = forecast(st)
  const diff = compare(base.forecast, f, st.events)
  const m = new Map<string, number>()
  diff.newlyRisky.forEach((r) => m.set(r.id, r.after))
  s.cache = { n: s.patches.length, risky: m }
  return m
}

const md = (iso: string) => { const [, m, d] = iso.split('-'); return `${+m}/${+d}` }

// 카드 결제일에 맞춘 출금일(오늘 기준 일수)
function billingOffset(dueDay: number, billingDay: number): number {
  const d = new Date(`${isoDay(dueDay)}T00:00:00Z`)
  const y = d.getUTCFullYear(), m = d.getUTCMonth()
  const target = d.getUTCDate() <= billingDay ? Date.UTC(y, m, billingDay) : Date.UTC(y, m + 1, billingDay)
  const today = new Date(`${isoDay(0)}T00:00:00Z`).getTime()
  return Math.round((target - today) / 86_400_000)
}

const maxDelayOfContract = (s: State, contractId: string) =>
  Math.max(0, ...s.graph.edges.filter((e) => e.type === 'GOVERNED_BY' && e.target === contractId).map((e) => s.payableDelay.get(e.source) ?? 0))

// ---------- 엣지 타입별 handler ----------
export const HANDLERS: Record<EdgeType, Handler> = {
  // 거래처 → 정산: 지연이면 날짜 이동, 폐업이면 미회수
  SETTLES: ({ origin, from, to, s }) => {
    if (origin !== 'source' || to.type !== 'settlement') return null
    const days = s.partnerDelay.get(from.id)
    if (days && from.type === 'partner' && from.role === 'sales') {
      const ev = evOf(to.id)
      return { patch: { id: to.id, kind: 'shift', days }, to: { status: 'at_risk', reason: `${to.label} ${days}일 지연${ev ? ` (${md(isoDay(ev.day))} → ${md(isoDay(ev.day + days))})` : ''}` } }
    }
    if (s.closed.has(from.id)) return { patch: { id: to.id, kind: 'remove' }, to: { status: 'triggered', reason: `${from.label} 폐업으로 ${to.label} 미회수` } }
    return null
  },
  // 정산 → 계좌: 정산이 늦거나 못 들어오면 그 날짜 잔액이 줄어든다 / 매출 하락이면 계좌에서 거슬러 올라가 정산액을 줄인다
  DEPOSITS_TO: ({ origin, from, to, s }) => {
    if (origin === 'target') {
      if (s.shock.type !== 'revenue_drop' || from.type !== 'account' || to.type !== 'settlement') return null
      const factor = 1 - s.shock.pct / 100
      const ev = evOf(to.id)
      return { patch: { id: to.id, kind: 'amount', factor }, to: { status: 'changed', reason: `${to.label} ${s.shock.pct}% 감소${ev ? ` (${won(ev.amount)} → ${won(Math.round(ev.amount * factor))})` : ''}` } }
    }
    const st = s.status.get(from.id)
    if (!st || (st.status !== 'at_risk' && st.status !== 'triggered')) return null
    return { to: { status: 'at_risk', reason: `${from.label}이 제때 들어오지 않아 해당 날짜 잔액이 줄어듭니다` } }
  },
  // 계좌 → 지급·고정비·대출: 잔액이 부족해지는 대상이 위험
  FUNDS: ({ origin, from, to, s }) => {
    if (origin !== 'source' || from.type !== 'account' || !s.status.has(from.id)) return null
    const p = risky(s).get(to.id)
    if (p === undefined) return null
    return { to: { status: 'at_risk', reason: `${to.label}${to.type === 'loan' ? ' 상환' : ' 지급'} 때 잔액이 모자랄 확률 ${Math.round(p * 100)}%` } }
  },
  // 지급 → 매입처: 매입처 지연 충격이면 지급일이 밀린다(대금 지급 지연)
  PAYS_TO: ({ origin, from, to, s }) => {
    if (origin !== 'target' || to.type !== 'payable') return null
    const days = s.partnerDelay.get(from.id)
    if (days) {
      s.payableDelay.set(to.id, days)
      return { patch: { id: to.id, kind: 'shift', days }, to: { status: 'changed', reason: `${to.label} 지급 ${days}일 지연` } }
    }
    if (s.closed.has(from.id)) return { to: { status: 'triggered', reason: `${from.label} 폐업으로 ${to.label}의 대금 수령처가 사라집니다` } }
    return null
  },
  // 카드 → 계좌: 카드로 결제한 지급은 카드 결제일에 계좌에서 출금
  CHARGED_TO: ({ origin, from, s }) => {
    if (origin !== 'source' || ![...s.paidWith.values()].includes(from.id)) return null
    return { to: { status: 'changed', reason: `${from.label} 대금이 매월 결제일에 사업용 계좌에서 출금됩니다` } }
  },
  // 지급 → 카드: 결제수단 변경이면 출금일이 카드 결제일로 이동
  PAID_WITH: ({ origin, from, to, s }) => {
    const sh = s.shock
    if (origin !== 'source' || sh.type !== 'payment_switch' || from.id !== sh.targetId || to.id !== sh.cardId || to.type !== 'card') return null
    const ev = evOf(from.id)
    if (!ev) return null
    s.paidWith.set(from.id, to.id)
    const day = billingOffset(ev.day, to.billingDay)
    return { patch: { id: from.id, kind: 'setDay', day }, to: { status: 'changed', reason: `${from.label} 출금일 ${md(isoDay(ev.day))} → ${md(isoDay(day))} (${to.label} 결제일)` } }
  },
  // 카드 → 지급: 조건을 충족하고 그 카드로 결제할 때만 할인
  BENEFIT_APPLIES: ({ origin, from, to, s }) => {
    if (origin !== 'source' || from.type !== 'card' || s.paidWith.get(to.id) !== from.id) return null
    const b = from.benefits.find((x) => x.appliesTo.includes(to.id))
    if (!b) return null
    const spend = s.shock.type === 'payment_switch' && s.shock.prevMonthSpend !== undefined ? s.shock.prevMonthSpend : from.prevMonthSpend
    const ok = b.minPrevMonthSpend === undefined || spend >= b.minPrevMonthSpend
    const ev = evOf(to.id)
    if (!ok) return { enqueue: false, to: { status: 'changed', reason: `${b.description} 미적용 (전월 실적 ${won(spend)} < 기준 ${won(b.minPrevMonthSpend ?? 0)})` } }
    return { patch: { id: to.id, kind: 'amount', factor: 1 - b.discountRate }, to: { status: 'changed', reason: `${b.description} 적용 (약 ${won(Math.round((ev?.amount ?? 0) * b.discountRate))} 할인)` } }
  },
  // 항목 → 계약서: 항목이 위험하면 계약의 조항이 문제가 될 수 있다 / 발동된 계약은 그 계약이 규율하는 대출로 번진다
  GOVERNED_BY: ({ origin, from, to, s }) => {
    if (origin === 'source') {
      if (to.type !== 'contract') return null
      const st = s.status.get(from.id)
      if (from.type === 'loan' && s.overdue.has(from.id)) return { to: { status: 'triggered', reason: `${from.label} 연체로 ${to.label}의 조항이 발동됩니다` } }
      if (from.type === 'payable' && (s.payableDelay.get(from.id) ?? 0) > 0) return { to: { status: 'at_risk', reason: `${from.label} 지급 지연이 ${to.label}의 조건에 걸립니다` } }
      if (st && (st.status === 'at_risk' || st.status === 'triggered') && from.type !== 'payable') return { to: { status: 'at_risk', reason: `${from.label}이 위험해져 ${to.label}의 조항을 확인해야 합니다` } }
      return null
    }
    // 계약 → 대출: 교차 발동된 계약의 대출은 기한이익을 잃을 수 있다
    if (from.type !== 'contract' || to.type !== 'loan') return null
    const cst = s.status.get(from.id)
    if (cst?.status === 'triggered' && !s.status.has(to.id)) return { to: { status: 'triggered', reason: `${from.label}이 발동되어 ${to.label}도 기한이익을 잃을 수 있습니다` } }
    return null
  },
  // 계약서 → 조항
  HAS_CLAUSE: ({ origin, from, to, s }) => {
    if (origin !== 'source' || to.type !== 'clause' || from.type !== 'contract') return null
    const cst = s.status.get(from.id)?.status
    if (!cst) return null
    const t = to.clauseType
    if (t === 'supply_stop') {
      const d = maxDelayOfContract(s, from.id)
      const limit = Number(to.params?.days ?? 30)
      if (d >= limit) return { to: { status: 'triggered', reason: `대금이 ${d}일 밀려 '${to.label}' 조항이 발동됩니다 (기준 ${limit}일)` } }
      if (d > 0) return { to: { status: 'at_risk', reason: `대금 ${d}일 지연 중, ${limit}일이 되면 공급 중단 조항이 발동됩니다` } }
      return null
    }
    if (t === 'payment_term') return maxDelayOfContract(s, from.id) > 0 ? { to: { status: 'at_risk', reason: `'${to.label}' 지급 조건을 넘깁니다` } } : null
    if (t === 'settlement_term') return cst === 'at_risk' || cst === 'triggered' ? { to: { status: 'at_risk', reason: `정산 지연으로 '${to.label}' 조건과 어긋납니다` } } : null
    if (t === 'acceleration' || t === 'cross_default') {
      if (cst === 'triggered') return { to: { status: 'triggered', reason: `'${to.label}' 발동: ${to.trigger} → ${to.effect}` } }
      return { to: { status: 'at_risk', reason: `'${to.label}': 연체되면 ${to.effect}` } }
    }
    if (t === 'termination' && cst !== 'changed') return { to: { status: 'at_risk', reason: `'${to.label}': ${to.trigger} 시 ${to.effect}` } }
    return null
  },
  // 조항 → 다른 계약: 발동된 교차 조항은 상대 계약을 발동시킨다
  CROSS_TRIGGERS: ({ origin, from, to, s }) => {
    if (origin !== 'source' || s.status.get(from.id)?.status !== 'triggered') return null
    if (s.status.has(to.id)) return null // 이미 발동된 계약으로 되돌아가지 않는다
    return { to: { status: 'triggered', reason: `${from.label} 조항이 ${to.label}을(를) 발동시킵니다` } }
  },
  // 정책 상품 → 대출: 대환 시 금리·상환액 재계산과 중도상환수수료
  REFINANCES: ({ origin, from, to, s }) => {
    const sh = s.shock
    if (origin !== 'source' || sh.type !== 'refinance' || from.id !== sh.productId || to.id !== sh.loanId || from.type !== 'policy_product' || to.type !== 'loan') return null
    const saving = Math.round((to.principal * (to.rate - from.rate)) / 100 / 12)
    const feeClause = s.graph.nodes.find((c) => c.type === 'clause' && c.contractId === to.contractId && c.clauseType === 'prepayment_fee')
    const fee = Math.round(to.principal * Number(feeClause?.type === 'clause' ? feeClause.params?.rate ?? 0 : 0))
    s.patches.push({ id: to.id, kind: 'amount', delta: -saving })
    if (fee > 0) s.patches.push({ kind: 'add', event: { id: 'REFI-FEE', label: '중도상환수수료', kind: 'loan', day: 3, amount: fee, direction: 'out' } })
    return { to: { status: 'changed', reason: `${to.label} 연 ${to.rate}% → ${from.rate}%: 월 상환액 ${won(saving)} 감소${fee ? `, 중도상환수수료 ${won(fee)}` : ''}` } }
  },
  // 신호 → 대상: 신호는 전파하지 않고 시나리오를 제안만 한다(suggestions 참고)
  SIGNALS: () => null,
}

// ---------- 본체 ----------
export function propagate(graph: FinanceGraph, shock: GraphShock): PropagationResult {
  const byId = new Map(graph.nodes.map((n) => [n.id, n]))
  const incident = new Map<string, GraphEdge[]>()
  let edges = graph.edges
  if (shock.type === 'payment_switch') {
    // 충격은 그래프 사본에 반영한다(입력 그래프는 바꾸지 않는다): 기존 결제수단을 끊고 새 카드와 잇는다
    edges = [...edges.filter((e) => !(e.type === 'PAID_WITH' && e.source === shock.targetId)), { id: `PAID_WITH:${shock.targetId}>${shock.cardId}:new`, source: shock.targetId, target: shock.cardId, type: 'PAID_WITH', label: '변경한 결제수단' }]
  }
  edges.forEach((e) => {
    incident.set(e.source, [...(incident.get(e.source) ?? []), e])
    incident.set(e.target, [...(incident.get(e.target) ?? []), e])
  })
  const g: FinanceGraph = { nodes: graph.nodes, edges }
  const s: State = { byId, incident, graph: g, shock, status: new Map(), patches: [], partnerDelay: new Map(), payableDelay: new Map(), closed: new Set(), overdue: new Set(), paidWith: new Map(), cache: null }
  // 현재 결제수단(기존 PAID_WITH)
  g.edges.filter((e) => e.type === 'PAID_WITH' && !(shock.type === 'payment_switch' && e.source === shock.targetId)).forEach((e) => s.paidWith.set(e.source, e.target))
  g.nodes.forEach((n) => { if (n.type === 'payable' && n.paymentMethod !== 'account') s.paidWith.set(n.id, n.paymentMethod) })

  const parent = new Map<string, string>()
  const edgeHop = new Map<string, number>()
  const set = (id: string, status: Status, reason: string, hop: number) => {
    const cur = s.status.get(id)
    if (!cur) s.status.set(id, { nodeId: id, status, hop, reason })
    else if (RANK[status] > RANK[cur.status]) s.status.set(id, { nodeId: id, status, hop: cur.hop, reason })
    else if (RANK[status] === RANK[cur.status] && !cur.reason.includes(reason)) s.status.set(id, { ...cur, reason: `${cur.reason} · ${reason}` })
  }

  // 충격 노드
  const starts: string[] = []
  const start = (id: string, status: Status, reason: string) => { starts.push(id); set(id, status, reason, 0) }
  switch (shock.type) {
    case 'settlement_delay': {
      const p = byId.get(shock.partnerId)
      if (p?.type !== 'partner') throw new Error(`거래처가 아닙니다: ${shock.partnerId}`)
      s.partnerDelay.set(p.id, shock.days)
      start(p.id, 'at_risk', p.role === 'sales' ? `${p.label}의 정산이 ${shock.days}일 늦어집니다` : `${p.label}에 대금을 ${shock.days}일 늦게 지급합니다`)
      break
    }
    case 'partner_closure': {
      const p = byId.get(shock.partnerId)
      if (p?.type !== 'partner') throw new Error(`거래처가 아닙니다: ${shock.partnerId}`)
      s.closed.add(p.id)
      start(p.id, 'triggered', `${p.label} 폐업`)
      break
    }
    case 'loan_default': {
      const l = byId.get(shock.loanId)
      if (l?.type !== 'loan') throw new Error(`대출이 아닙니다: ${shock.loanId}`)
      s.overdue.add(l.id)
      start(l.id, 'triggered', `${l.label} 연체`)
      break
    }
    case 'payment_switch': {
      const t = byId.get(shock.targetId)
      if (!t || (t.type !== 'payable' && t.type !== 'fixed_cost')) throw new Error(`결제수단을 바꿀 수 없는 노드입니다: ${shock.targetId}`)
      start(t.id, 'changed', `${t.label} 결제수단 변경`)
      break
    }
    case 'rate_up': {
      g.nodes.forEach((n) => {
        if (n.type === 'loan' && n.rateType === 'variable') {
          const add = Math.round((n.principal * (shock.pp / 100)) / 12)
          s.patches.push({ id: n.id, kind: 'amount', delta: add })
          start(n.id, 'changed', `${n.label} 변동금리 +${shock.pp}%p: 월 상환액 +${won(add)}`)
        }
      })
      break
    }
    case 'current': {
      const f0 = base.forecast
      start('ACC', f0.minP50 < 0 ? 'at_risk' : 'changed', `예상 최저 잔액 ${won(f0.minP50)}${f0.firstShortDay ? `, ${md(isoDay(f0.firstShortDay))}부터 잔액 부족` : ''}`)
      for (const [id, d] of Object.entries(knownDelays)) {
        const n = byId.get(id)
        if (n?.type === 'settlement') start(id, 'at_risk', `${n.label} ${d}일 지연 확정 (${md(n.dueDate)} 예정)`)
      }
      break
    }
    case 'revenue_drop': {
      s.patches.push({ kind: 'sales', factor: 1 - shock.pct / 100 })
      start('ACC', 'at_risk', `매출이 ${shock.pct}% 줄어 현장 매출과 정산 입금이 함께 감소합니다`)
      break
    }
    case 'refinance': {
      const p = byId.get(shock.productId)
      if (p?.type !== 'policy_product') throw new Error(`정책 상품이 아닙니다: ${shock.productId}`)
      start(p.id, 'changed', `${p.label}로 대환`)
      break
    }
  }

  // BFS (최대 MAX_HOPS홉)
  const visited = new Set(starts)
  let frontier = starts.map((id) => ({ id, hop: 0 }))
  let maxHop = 0
  while (frontier.length) {
    const next: { id: string; hop: number }[] = []
    for (const { id, hop } of frontier) {
      if (hop >= MAX_HOPS) continue
      for (const e of incident.get(id) ?? []) {
        const origin = e.source === id ? 'source' : 'target'
        const otherId = origin === 'source' ? e.target : e.source
        const eff = HANDLERS[e.type]({ edge: e, origin, from: byId.get(id)!, to: byId.get(otherId)!, s })
        if (!eff) continue
        if (eff.patch) s.patches.push(eff.patch)
        edgeHop.set(e.id, Math.min(edgeHop.get(e.id) ?? 99, hop + 1))
        if (eff.to) set(otherId, eff.to.status, eff.to.reason, hop + 1)
        if (eff.enqueue === false || visited.has(otherId)) continue
        visited.add(otherId)
        parent.set(otherId, id)
        maxHop = Math.max(maxHop, hop + 1)
        next.push({ id: otherId, hop: hop + 1 })
      }
    }
    frontier = next
  }
  // 위험해진 대출은 계좌에서 나가는 상환 엣지도 경로에 포함한다
  g.nodes.forEach((n) => {
    if (n.type === 'loan' && s.status.has(n.id)) {
      const f = g.edges.find((e) => e.type === 'FUNDS' && e.target === n.id)
      if (f && !edgeHop.has(f.id)) edgeHop.set(f.id, (s.status.get(n.id)?.hop ?? 1))
    }
  })

  // 잔액 계산
  const st = applyPatches(s.patches)
  const f: Forecast = forecast(st)
  const diff = compare(base.forecast, f, st.events)
  const delta = f.minP50 - base.forecast.minP50
  const riskMap = new Map<string, number>(diff.newlyRisky.map((r) => [r.id, r.after]))

  // 마무리: 금리 상승처럼 현금이 직접 부족해지는 대상 표시, 개선 시나리오는 개선 표시
  if (shock.type === 'rate_up' || shock.type === 'refinance') {
    s.status.forEach((v) => {
      const n = byId.get(v.nodeId)
      if (n?.type === 'loan' && riskMap.has(n.id)) set(n.id, 'at_risk', `${n.label} 상환 때 잔액이 모자랄 확률 ${Math.round((riskMap.get(n.id) ?? 0) * 100)}%`, v.hop)
    })
  }
  if ((shock.type === 'payment_switch' || shock.type === 'refinance') && delta > 0) {
    s.status.forEach((v) => { if (v.status === 'changed') s.status.set(v.nodeId, { ...v, status: 'improved', reason: v.reason }) })
    s.status.set('ACC', { nodeId: 'ACC', status: 'improved', hop: 1, reason: `최저 잔액이 ${won(delta)} 개선됩니다` })
  }

  // 경로(충격 노드 → 말단)
  const hasChild = new Set(parent.values())
  const paths: string[][] = []
  for (const id of parent.keys()) {
    if (hasChild.has(id)) continue
    const p: string[] = [id]
    for (let cur = parent.get(id); cur !== undefined; cur = parent.get(cur)) p.unshift(cur)
    paths.push(p)
  }

  const suggestions = g.nodes.flatMap((n) => (n.type === 'signal' && (s.status.has(n.targetId) || starts.includes(n.targetId)) ? [{ signalId: n.id, targetId: n.targetId, text: n.text }] : []))
  const notes = [...s.status.values()].sort((a, b) => a.hop - b.hop || RANK[b.status] - RANK[a.status]).map((e) => e.reason)

  const repayments: Repayment[] = g.nodes.flatMap((n) => {
    if (n.type !== 'loan') return []
    const e = s.status.get(n.id)
    if (!e || (e.status !== 'at_risk' && e.status !== 'triggered')) return []
    return [{ id: n.id, label: n.label, date: n.nextPaymentDate, amount: n.nextPaymentAmount, prob: riskMap.get(n.id) ?? (e.status === 'triggered' ? 1 : 0) }]
  })

  return {
    shock,
    nodes: s.status,
    edges: edgeHop,
    paths,
    hops: maxHop,
    patches: s.patches,
    suggestions,
    balance: { baseMinP50: base.forecast.minP50, minP50: f.minP50, minDay: f.minDay, baseFirstShortDay: base.forecast.firstShortDay, firstShortDay: f.firstShortDay, repayments },
    notes,
  }
}
