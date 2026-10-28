// Graph RAG 검색 계층(M7+M8 파일럿). 사용자 상황(거래처·정산·대출)과 금융상품 정보를 그래프로 보고,
// 계획(Plan)이 가리키는 앵커에서 이웃 노드를 따라가며 근거(Evidence)를 모은다.
// 근거는 ID(E1…)가 붙어 LLM 컨텍스트, 화면 표시, 응답 검증(M9)에 같이 쓰인다.
import { alertWindowEvents as baseEvents, business, dayLabel, partners, policyProducts, won } from './data.ts'
import type { Shock } from './engine.ts'

export interface Evidence {
  id: string
  kind: 'situation' | 'product' | 'result'
  text: string
  nodes: string[]
}

export interface RetrievalResult {
  evidence: Evidence[]
  nodeIds: Set<string>
}

const evt = (id: string) => baseEvents.find((e) => e.id === id)!

export function retrieve(shocks: Shock[]): RetrievalResult {
  const evidence: Evidence[] = []
  const nodeIds = new Set<string>(['ACC'])
  const add = (kind: Evidence['kind'], text: string, nodes: string[]) => {
    evidence.push({ id: `E${evidence.length + 1}`, kind, text, nodes })
    nodes.forEach((n) => nodeIds.add(n))
  }

  add('situation', `사업용 계좌 현재 잔액은 ${won(business.startBalance)}이고 최소 유지 잔액은 ${won(business.minBalance)}입니다.`, ['ACC'])

  for (const k of shocks) {
    if ((k.type === 'settlement_delay' || k.type === 'partner_closure') && k.partnerId) {
      const p = partners.find((q) => q.id === k.partnerId)!
      const settles = baseEvents.filter((e) => e.kind === 'settlement' && e.partnerId === p.id)
      const s = settles[0]
      add('situation', `${p.name}는 ${p.taxStatus}이고 정산은 평균 ${s.delay?.mean ?? 0}일(±${s.delay?.sd ?? 0}일) 늦게 들어오는 편입니다.`, [p.id])
      settles.forEach((e) => add('situation', `${p.name} 정산 ${won(e.amount)}이 ${dayLabel(e.day)}에 사업용 계좌로 들어올 예정입니다.`, [p.id, e.id, 'ACC']))
      // 2~3홉: 계좌 → 정산 직후 14일 안의 지급
      const lastIn = Math.max(...settles.map((e) => e.day))
      baseEvents
        .filter((e) => e.direction === 'out' && e.day >= Math.min(...settles.map((x) => x.day)) && e.day <= lastIn + 14)
        .sort((a, b) => a.day - b.day)
        .forEach((e) => add('situation', `계좌에서 ${dayLabel(e.day)}에 ${e.label} ${won(e.amount)}이 나갑니다.`, [e.id]))
    }
    if (k.type === 'revenue_drop') {
      const total = baseEvents.filter((e) => e.kind === 'settlement').reduce((a, e) => a + e.amount, 0)
      add('situation', `4주 안에 받을 정산 합계는 ${won(total)}이고 일 평균 현장 매출은 ${won(business.salesPerDay)}입니다.`, baseEvents.filter((e) => e.kind === 'settlement').map((e) => e.id))
    }
    if (k.type === 'rate_up') {
      baseEvents.filter((e) => e.floatingRate && e.loanId).forEach((e) => {
        add('situation', `${e.label}은 변동금리이고 잔액 ${won(business.loanBalances[e.loanId!] ?? 0)}에 대해 월 ${won(e.amount)}이 ${dayLabel(e.day)}에 상환됩니다.`, [e.id])
      })
    }
    if (k.type === 'new_loan') {
      policyProducts.forEach((p, i) => add('product', `${p.name}(${p.agency}): ${p.rate}, ${p.limit}. 비교 정보이며 권유가 아닙니다.`, [`PP${i + 1}`]))
      baseEvents.filter((e) => e.kind === 'loan').forEach((e) => add('situation', `기존 ${e.label} ${won(e.amount)}이 ${dayLabel(e.day)}에 예정되어 있습니다.`, [e.id]))
    }
  }
  return { evidence, nodeIds }
}

export const eventLabel = (id: string) => evt(id)?.label ?? id
