// 금융지도 그래프의 타입과 합성 데이터. 렌더링·레이아웃·전파 로직과 분리해 둔다(Graph RAG 검색 대상이기도 하다).
// P*, S*, Y*, F*, L* ID는 data.ts / engine.ts 이벤트와 같아서 시뮬레이션 결과를 그대로 얹을 수 있다.
// 모든 값은 시연용 합성 데이터다.
import { baseEvents, business, isoDay, partners as basePartners, policyProducts } from '../data.ts'

// ---------- 타입 ----------
export type EdgeType =
  | 'SETTLES' | 'DEPOSITS_TO' | 'FUNDS' | 'PAYS_TO' | 'CHARGED_TO' | 'PAID_WITH'
  | 'BENEFIT_APPLIES' | 'GOVERNED_BY' | 'HAS_CLAUSE' | 'CROSS_TRIGGERS' | 'REFINANCES' | 'SIGNALS'

export interface GraphEdge {
  id: string
  source: string
  target: string
  type: EdgeType
  label: string
}

interface Base { id: string; label: string }

export interface AccountNode extends Base { type: 'account'; balance: number; minBalance: number }
export interface PartnerNode extends Base { type: 'partner'; role: 'sales' | 'purchase'; bizStatus: 'active' | 'suspended' | 'closed' }
export interface SettlementNode extends Base { type: 'settlement'; amount: number; dueDate: string; partnerId: string; delayRisk: number }
export interface PayableNode extends Base { type: 'payable'; amount: number; dueDate: string; partnerId: string; paymentMethod: 'account' | string }
export interface FixedCostNode extends Base { type: 'fixed_cost'; amount: number; dueDay: number; contractId?: string }
export interface LoanNode extends Base {
  type: 'loan'; principal: number; rate: number; rateType: 'fixed' | 'variable'
  nextPaymentDate: string; nextPaymentAmount: number; contractId: string
}
export interface Benefit {
  id: string
  description: string
  discountRate: number // 0.02 = 2%
  appliesTo: string[] // payable·fixed_cost ID
  minPrevMonthSpend?: number // 전월 실적 조건
}
export interface CardNode extends Base { type: 'card'; billingDay: number; limit: number; prevMonthSpend: number; benefits: Benefit[] }
export interface ContractNode extends Base { type: 'contract'; kind: 'lease' | 'loan' | 'supply' | 'sales'; counterparty: string; period: string }
export type ClauseType = 'acceleration' | 'cross_default' | 'prepayment_fee' | 'termination' | 'supply_stop' | 'payment_term' | 'settlement_term'
export interface ClauseNode extends Base {
  type: 'clause'; clauseType: ClauseType; trigger: string; effect: string; contractId: string
  params?: Record<string, number | string>
}
export interface PolicyProductNode extends Base { type: 'policy_product'; rate: number; limit: number; source: string; collectedAt: string }
export interface SignalNode extends Base { type: 'signal'; source: 'message' | 'news' | 'nts' | 'rate'; text: string; date: string; targetId: string }

export type GraphNode =
  | AccountNode | PartnerNode | SettlementNode | PayableNode | FixedCostNode | LoanNode | CardNode
  | ContractNode | ClauseNode | PolicyProductNode | SignalNode
export type NodeType = GraphNode['type']

export interface FinanceGraph { nodes: GraphNode[]; edges: GraphEdge[] }

// ---------- 합성 데이터 ----------
const ev = (id: string) => baseEvents.find((e) => e.id === id)!
const partnerName = (id: string) => basePartners.find((p) => p.id === id)!.name

// 정산이 3일 넘게 늦을 확률(정규 근사). 시연용 입력값이며 시뮬레이션은 engine.ts의 분포를 쓴다.
const erf = (x: number) => {
  const t = 1 / (1 + 0.3275911 * Math.abs(x))
  const y = 1 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * Math.exp(-x * x)
  return x >= 0 ? y : -y
}
const delayRiskOf = (mean: number, sd: number) => Math.round((1 - 0.5 * (1 + erf((3 - mean) / (sd * Math.SQRT2)))) * 100) / 100

const bizStatus = (s: string): PartnerNode['bizStatus'] => (s === '폐업' ? 'closed' : s === '휴업' ? 'suspended' : 'active')

const partnerNodes: PartnerNode[] = basePartners.map((p) => ({
  id: p.id, label: p.name, type: 'partner', role: p.role === 'sales' ? 'sales' : 'purchase', bizStatus: bizStatus(p.taxStatus),
}))

const settlementNodes: SettlementNode[] = ['S1', 'S2', 'S3'].map((id) => {
  const e = ev(id)
  return { id, label: `${partnerName(e.partnerId!)} 정산`, type: 'settlement', amount: e.amount, dueDate: isoDay(e.day), partnerId: e.partnerId!, delayRisk: delayRiskOf(e.delay!.mean, e.delay!.sd) }
})

const payableNodes: PayableNode[] = ['Y1', 'Y2'].map((id) => {
  const e = ev(id)
  const date = isoDay(e.day)
  return { id, label: `${partnerName(e.partnerId!)} 매입 대금 (${+date.slice(5, 7)}/${+date.slice(8, 10)})`, type: 'payable', amount: e.amount, dueDate: isoDay(e.day), partnerId: e.partnerId!, paymentMethod: 'account' }
})

const fixedNodes: FixedCostNode[] = [
  { id: 'F1', label: '임대료', type: 'fixed_cost', amount: ev('F1').amount, dueDay: 5, contractId: 'K_LEASE' },
  { id: 'F2', label: '인건비', type: 'fixed_cost', amount: ev('F2').amount, dueDay: 10 },
  { id: 'F3', label: '공과금', type: 'fixed_cost', amount: ev('F3').amount, dueDay: 15 },
]

const loanSpec = {
  L1: { label: '운영자금대출', rate: 6.2, rateType: 'variable' as const, contractId: 'K_L1' },
  L2: { label: '시설자금대출', rate: 5.4, rateType: 'fixed' as const, contractId: 'K_L2' },
}
const loanNodes: LoanNode[] = (['L1', 'L2'] as const).map((id) => ({
  id, label: loanSpec[id].label, type: 'loan', principal: business.loanBalances[id], rate: loanSpec[id].rate, rateType: loanSpec[id].rateType,
  nextPaymentDate: isoDay(ev(id).day), nextPaymentAmount: ev(id).amount, contractId: loanSpec[id].contractId,
}))

const cardNodes: CardNode[] = [
  { id: 'C1', label: 'A카드(사업자)', type: 'card', billingDay: 25, limit: 15_000_000, prevMonthSpend: 1_820_000,
    benefits: [{ id: 'C1-b1', description: '식자재·도매 업종 2% 청구할인', discountRate: 0.02, appliesTo: ['Y1', 'Y2'], minPrevMonthSpend: 1_500_000 }] },
  { id: 'C2', label: 'B카드(사업자)', type: 'card', billingDay: 14, limit: 10_000_000, prevMonthSpend: 600_000,
    benefits: [{ id: 'C2-b1', description: '공과금 자동납부 1% 할인', discountRate: 0.01, appliesTo: ['F3'] }] },
]
// 현재 결제수단: 공과금은 B카드, 대성유통 매입 대금은 계좌이체
const payWith: Record<string, string> = { F3: 'C2' }

const contractNodes: ContractNode[] = [
  { id: 'K_LEASE', label: '임대차계약', type: 'contract', kind: 'lease', counterparty: '임대인', period: '2025-03 ~ 2027-03' },
  { id: 'K_L1', label: '운영자금 대출약정', type: 'contract', kind: 'loan', counterparty: '○○은행', period: '2023-09 ~ 2028-09' },
  { id: 'K_L2', label: '시설자금 대출약정', type: 'contract', kind: 'loan', counterparty: '△△은행', period: '2025-03 ~ 2030-03' },
  { id: 'K_SUP', label: '대성유통 공급계약', type: 'contract', kind: 'supply', counterparty: '대성유통', period: '2026-01 ~ 2027-01' },
  { id: 'K_SALES', label: '한빛식자재 판매계약', type: 'contract', kind: 'sales', counterparty: '한빛식자재', period: '2026-03 ~ 2027-03' },
]

const clauseNodes: ClauseNode[] = [
  { id: 'CL_LEASE1', label: '차임 연체 해지', type: 'clause', clauseType: 'termination', trigger: '차임 3회 연체', effect: '임대인이 계약을 해지할 수 있음', contractId: 'K_LEASE', params: { count: 3 } },
  { id: 'CL_L1a', label: '연체 시 기한이익상실', type: 'clause', clauseType: 'acceleration', trigger: '운영자금대출 상환 연체', effect: '잔여 원금 전액 즉시 상환 요구', contractId: 'K_L1' },
  { id: 'CL_L1b', label: '교차 기한이익상실', type: 'clause', clauseType: 'cross_default', trigger: '다른 대출 연체', effect: '운영자금대출도 기한이익 상실', contractId: 'K_L1' },
  { id: 'CL_L1c', label: '중도상환수수료 1.2%', type: 'clause', clauseType: 'prepayment_fee', trigger: '대환·중도상환', effect: '상환 원금의 1.2% 수수료', contractId: 'K_L1', params: { rate: 0.012 } },
  { id: 'CL_L2a', label: '연체 시 기한이익상실', type: 'clause', clauseType: 'acceleration', trigger: '시설자금대출 상환 연체', effect: '잔여 원금 전액 즉시 상환 요구', contractId: 'K_L2' },
  { id: 'CL_L2b', label: '교차 기한이익상실', type: 'clause', clauseType: 'cross_default', trigger: '다른 대출 연체', effect: '시설자금대출도 기한이익 상실', contractId: 'K_L2' },
  { id: 'CL_SUP1', label: '월말 마감·익월 10일 지급', type: 'clause', clauseType: 'payment_term', trigger: '매월 말 마감', effect: '익월 10일까지 대금 지급', contractId: 'K_SUP', params: { payDay: 10 } },
  { id: 'CL_SUP2', label: '미지급 30일 공급 중단', type: 'clause', clauseType: 'supply_stop', trigger: '대금 30일 이상 미지급', effect: '대성유통이 공급을 중단할 수 있음', contractId: 'K_SUP', params: { days: 30 } },
  { id: 'CL_SALES1', label: '월말 마감·익월 15일 정산', type: 'clause', clauseType: 'settlement_term', trigger: '매월 말 마감', effect: '익월 15일 정산 입금', contractId: 'K_SALES', params: { payDay: 15 } },
]

const policyNodes: PolicyProductNode[] = [
  { id: 'PP1', label: policyProducts[0].name, type: 'policy_product', rate: 3.0, limit: 70_000_000, source: policyProducts[0].agency, collectedAt: isoDay(0) },
]

const signalNodes: SignalNode[] = [
  { id: 'SG1', label: '한빛식자재 정산 지연 메시지', type: 'signal', source: 'message', text: '한빛식자재: 이번 달 정산이 2주 정도 늦어질 것 같습니다', date: isoDay(0), targetId: 'P1' },
  { id: 'SG2', label: '기준금리 인상 가능성', type: 'signal', source: 'rate', text: '기준금리 인상 가능성', date: isoDay(0), targetId: 'L1' },
]

const accountNode: AccountNode = { id: 'ACC', label: '사업용 계좌', type: 'account', balance: business.startBalance, minBalance: business.minBalance }

const nodes: GraphNode[] = [
  accountNode, ...partnerNodes, ...settlementNodes, ...payableNodes, ...fixedNodes, ...loanNodes, ...cardNodes,
  ...contractNodes, ...clauseNodes, ...policyNodes, ...signalNodes,
]

let n = 0
const edge = (source: string, target: string, type: EdgeType, label: string): GraphEdge => ({ id: `${type}:${source}>${target}:${n++}`, source, target, type, label })

const edges: GraphEdge[] = [
  ...settlementNodes.flatMap((s) => [edge(s.partnerId, s.id, 'SETTLES', '정산'), edge(s.id, 'ACC', 'DEPOSITS_TO', '입금')]),
  ...[...payableNodes, ...fixedNodes, ...loanNodes].map((t) => edge('ACC', t.id, 'FUNDS', '출금')),
  ...payableNodes.map((p) => edge(p.id, p.partnerId, 'PAYS_TO', '대금 지급')),
  ...cardNodes.map((c) => edge(c.id, 'ACC', 'CHARGED_TO', `매월 ${c.billingDay}일 청구`)),
  ...Object.entries(payWith).map(([from, card]) => edge(from, card, 'PAID_WITH', '현재 결제수단')),
  ...cardNodes.flatMap((c) => c.benefits.flatMap((b) => b.appliesTo.map((t) => edge(c.id, t, 'BENEFIT_APPLIES', b.description)))),
  ...loanNodes.map((l) => edge(l.id, l.contractId, 'GOVERNED_BY', '계약 근거')),
  edge('F1', 'K_LEASE', 'GOVERNED_BY', '계약 근거'),
  edge('Y1', 'K_SUP', 'GOVERNED_BY', '계약 근거'),
  edge('Y2', 'K_SUP', 'GOVERNED_BY', '계약 근거'),
  edge('S1', 'K_SALES', 'GOVERNED_BY', '계약 근거'),
  ...clauseNodes.map((c) => edge(c.contractId, c.id, 'HAS_CLAUSE', '조항')),
  edge('CL_L1b', 'K_L2', 'CROSS_TRIGGERS', '교차 발동'),
  edge('CL_L2b', 'K_L1', 'CROSS_TRIGGERS', '교차 발동'),
  edge('PP1', 'L1', 'REFINANCES', '대환 후보'),
  ...signalNodes.map((s) => edge(s.id, s.targetId, 'SIGNALS', '신호')),
]

export const graph: FinanceGraph = { nodes, edges }
export const nodeById = new Map<string, GraphNode>(nodes.map((x) => [x.id, x]))

export const edgesOf = (id: string) => edges.filter((e) => e.source === id || e.target === id)
