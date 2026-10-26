// 그래프 질의 함수: 노드 상세 패널과(이후) Graph RAG 검색이 같이 쓴다.
import { graph, nodeById, type CardNode, type ContractNode, type GraphEdge, type GraphNode } from '../data/financeGraph.ts'
import { won } from '../data.ts'
import { CLAUSE_LABEL } from './describe.ts'

export interface Reach { node: GraphNode; via: GraphEdge[] }

// 엣지 방향을 따라 최대 depth홉까지. down = 이 노드가 영향을 주는 것, up = 이 노드가 영향을 받는 것.
export function reach(id: string, dir: 'down' | 'up', depth = 2): Reach[] {
  const out: Reach[] = []
  const seen = new Set<string>([id])
  let frontier: Reach[] = [{ node: nodeById.get(id)!, via: [] }]
  for (let d = 0; d < depth; d++) {
    const next: Reach[] = []
    for (const cur of frontier) {
      for (const e of graph.edges) {
        const from = dir === 'down' ? e.source : e.target
        const to = dir === 'down' ? e.target : e.source
        if (from !== cur.node.id || seen.has(to)) continue
        seen.add(to)
        const r = { node: nodeById.get(to)!, via: [...cur.via, e] }
        out.push(r)
        next.push(r)
      }
    }
    frontier = next
  }
  return out
}

export function clausesOf(contract: ContractNode) {
  return graph.nodes.flatMap((n) => (n.type === 'clause' && n.contractId === contract.id ? [{ ...n, kindLabel: CLAUSE_LABEL[n.clauseType] ?? n.clauseType }] : []))
}

export interface BenefitStatus {
  description: string
  condition: string
  met: boolean | null // null = 조건 없음
  targets: { id: string; label: string; payingWith: string; applied: boolean }[]
}

// 카드 혜택: 전월 실적 조건 충족 여부 + 현재 이 카드로 결제 중인 항목만 혜택이 적용된다.
export function benefitStatus(card: CardNode): BenefitStatus[] {
  return card.benefits.map((b) => {
    const met = b.minPrevMonthSpend === undefined ? null : card.prevMonthSpend >= b.minPrevMonthSpend
    const targets = b.appliesTo.map((tid) => {
      const t = nodeById.get(tid)!
      const paid = t.type === 'payable' ? t.paymentMethod : graph.edges.some((e) => e.type === 'PAID_WITH' && e.source === tid && e.target === card.id) ? card.id : 'account'
      return { id: tid, label: t.label, payingWith: paid === 'account' ? '계좌이체' : (nodeById.get(paid)?.label ?? paid), applied: paid === card.id && met !== false }
    })
    return {
      description: b.description,
      condition: b.minPrevMonthSpend === undefined ? '조건 없음' : `전월 실적 ${won(card.prevMonthSpend)} / 기준 ${won(b.minPrevMonthSpend)}`,
      met,
      targets,
    }
  })
}

// 노드에서 시작할 수 있는 시나리오
export type ScenarioKind = 'settlement_delay' | 'loan_default' | 'payment_switch' | 'rate_up' | 'revenue_drop' | 'partner_closure' | 'current'
export interface ScenarioStart { kind: ScenarioKind; targetId: string }

export function scenarioFor(n: GraphNode): ScenarioStart | null {
  switch (n.type) {
    case 'partner': return n.role === 'sales' ? { kind: 'settlement_delay', targetId: n.id } : { kind: 'partner_closure', targetId: n.id }
    case 'settlement': return { kind: 'settlement_delay', targetId: n.partnerId }
    case 'loan': return { kind: 'loan_default', targetId: n.id }
    case 'payable': case 'fixed_cost': return { kind: 'payment_switch', targetId: n.id }
    case 'card': return { kind: 'payment_switch', targetId: n.benefits[0]?.appliesTo[0] ?? n.id }
    case 'contract': {
      const loan = graph.nodes.find((x) => x.type === 'loan' && x.contractId === n.id)
      return loan ? { kind: 'loan_default', targetId: loan.id } : null
    }
    case 'clause': { const c = nodeById.get(n.contractId); return c?.type === 'contract' ? scenarioFor(c) : null }
    case 'signal': {
      const t = nodeById.get(n.targetId)
      if (!t) return null
      if (n.source === 'rate') return { kind: 'rate_up', targetId: t.id }
      return scenarioFor(t)
    }
    case 'policy_product': return null
    case 'account': return { kind: 'revenue_drop', targetId: n.id }
  }
}

export const SCENARIO_LABEL: Record<ScenarioKind, string> = {
  settlement_delay: '정산 지연', loan_default: '대출 연체', payment_switch: '결제수단 변경', rate_up: '금리 상승', revenue_drop: '매출 하락', partner_closure: '거래처 폐업', current: '현재 상황',
}
