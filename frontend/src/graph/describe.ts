// 노드를 화면에 보여줄 문자열로 바꾸는 함수들. 금액·날짜는 전부 노드 속성에서 만든다(하드코딩 금지).
import { won } from '../data.ts'
import type { EdgeType, GraphNode, NodeType } from '../data/financeGraph.ts'

export type Group = 'cashflow' | 'partner' | 'card' | 'loanContract' | 'clause' | 'signal'

export const GROUPS: { id: Group; label: string }[] = [
  { id: 'cashflow', label: '현금흐름' },
  { id: 'partner', label: '거래처' },
  { id: 'card', label: '카드' },
  { id: 'loanContract', label: '대출·계약' },
  { id: 'clause', label: '조항' },
  { id: 'signal', label: '신호' },
]
// 사업용 계좌는 어느 그룹에도 속하지 않아 항상 보인다.
const GROUP_OF: Partial<Record<NodeType, Group>> = {
  settlement: 'cashflow', payable: 'cashflow', fixed_cost: 'cashflow',
  partner: 'partner', card: 'card',
  loan: 'loanContract', contract: 'loanContract', policy_product: 'loanContract',
  clause: 'clause', signal: 'signal',
}
export const groupOf = (t: NodeType): Group | null => GROUP_OF[t] ?? null

export const TYPE_LABEL: Record<NodeType, string> = {
  account: '사업용 계좌', partner: '거래처', settlement: '받을 돈', payable: '줄 돈', fixed_cost: '고정비', loan: '대출', card: '카드',
  contract: '계약서', clause: '계약 조항', policy_product: '정책 상품', signal: '신호',
}

export const EDGE_LABEL: Record<EdgeType, string> = {
  SETTLES: '정산', DEPOSITS_TO: '입금', FUNDS: '출금 재원', PAYS_TO: '대금 수령', CHARGED_TO: '카드 청구', PAID_WITH: '결제수단',
  BENEFIT_APPLIES: '카드 혜택', GOVERNED_BY: '계약 근거', HAS_CLAUSE: '조항', CROSS_TRIGGERS: '교차 발동', REFINANCES: '대환 후보', SIGNALS: '신호',
}

export const CLAUSE_LABEL: Record<string, string> = {
  acceleration: '기한이익상실', cross_default: '교차 기한이익상실', prepayment_fee: '중도상환수수료', termination: '계약 해지',
  supply_stop: '공급 중단', payment_term: '지급 조건', settlement_term: '정산 조건',
}

export const md = (iso: string) => {
  const [, m, d] = iso.split('-')
  return `${+m}/${+d}`
}

export function nodeSub(n: GraphNode): string {
  switch (n.type) {
    case 'account': return `잔액 ${won(n.balance)}`
    case 'partner': return n.role === 'sales' ? '매출처' : '매입처'
    case 'settlement': return `${won(n.amount)} · ${md(n.dueDate)}`
    case 'payable': return `${won(n.amount)} · ${md(n.dueDate)}`
    case 'fixed_cost': return `${won(n.amount)} · 매월 ${n.dueDay}일`
    case 'loan': return `${won(n.nextPaymentAmount)} · ${md(n.nextPaymentDate)} · ${n.rateType === 'variable' ? '변동' : '고정'} ${n.rate}%`
    case 'card': return `결제일 ${n.billingDay}일`
    case 'contract': return n.counterparty
    case 'clause': return ''
    case 'policy_product': return `연 ${n.rate}% · 한도 ${won(n.limit)}`
    case 'signal': return ''
  }
}

export function nodeLines(n: GraphNode): [string, string][] {
  switch (n.type) {
    case 'account': return [['현재 잔액', won(n.balance)], ['최소 유지 잔액', won(n.minBalance)]]
    case 'partner': return [['구분', n.role === 'sales' ? '매출처(정산 받음)' : '매입처(대금 지급)'], ['사업자 상태', { active: '계속사업자', suspended: '휴업', closed: '폐업' }[n.bizStatus]]]
    case 'settlement': return [['금액', won(n.amount)], ['예정일', md(n.dueDate)], ['3일 넘게 늦을 확률', `${Math.round(n.delayRisk * 100)}%`]]
    case 'payable': return [['금액', won(n.amount)], ['지급일', md(n.dueDate)], ['결제수단', n.paymentMethod === 'account' ? '계좌이체' : n.paymentMethod]]
    case 'fixed_cost': return [['금액', won(n.amount)], ['지급일', `매월 ${n.dueDay}일`]]
    case 'loan': return [['잔액', won(n.principal)], ['금리', `연 ${n.rate}% (${n.rateType === 'variable' ? '변동' : '고정'})`], ['다음 상환', `${won(n.nextPaymentAmount)} · ${md(n.nextPaymentDate)}`]]
    case 'card': return [['결제일', `매월 ${n.billingDay}일`], ['한도', won(n.limit)], ['전월 실적', won(n.prevMonthSpend)], ...n.benefits.map((b): [string, string] => ['혜택', `${b.description}${b.minPrevMonthSpend ? ` (전월 실적 ${won(b.minPrevMonthSpend)} 이상)` : ''}`])]
    case 'contract': return [['상대방', n.counterparty], ['기간', n.period]]
    case 'clause': return [['조항 종류', n.clauseType], ['발동 조건', n.trigger], ['효과', n.effect]]
    case 'policy_product': return [['금리', `연 ${n.rate}%`], ['한도', won(n.limit)], ['출처', n.source], ['수집일', md(n.collectedAt)]]
    case 'signal': return [['출처', { message: '메시지', news: '뉴스', nts: '국세청', rate: '금리' }[n.source]], ['내용', n.text], ['날짜', md(n.date)]]
  }
}
