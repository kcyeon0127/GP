// 그래프의 속성에서 계산하는 절감·혜택 후보. 금액은 전부 노드 데이터로 계산한다.
import { graph, nodeById } from '../data/financeGraph.ts'
import { won } from '../data.ts'

export interface Opportunity { id: string; title: string; body: string; nodes: string[] }

export function opportunities(): Opportunity[] {
  const out: Opportunity[] = []

  for (const n of graph.nodes) {
    if (n.type !== 'card') continue
    for (const b of n.benefits) {
      const targets = b.appliesTo.map((id) => nodeById.get(id)).filter((t) => t?.type === 'payable' || t?.type === 'fixed_cost')
      const notYet = targets.filter((t) => t && t.type === 'payable' && t.paymentMethod !== n.id)
      if (!notYet.length) continue
      const total = notYet.reduce((a, t) => a + (t && 'amount' in t ? t.amount : 0), 0)
      const met = b.minPrevMonthSpend === undefined || n.prevMonthSpend >= b.minPrevMonthSpend
      out.push({
        id: b.id,
        title: `${n.label}로 결제하면 혜택`,
        body: `${notYet.map((t) => t!.label).join(', ')} 합계 ${won(total)}을 ${n.label}로 결제하면 ${b.description}으로 약 ${won(Math.round(total * b.discountRate))}을 아낄 수 있고, 출금일이 카드 결제일(${n.billingDay}일)로 이동합니다. ` +
          (b.minPrevMonthSpend !== undefined ? `전월 실적 ${won(n.prevMonthSpend)}로 조건(${won(b.minPrevMonthSpend)} 이상)을 ${met ? '충족' : '충족하지 못'}합니다.` : ''),
        nodes: [n.id, ...notYet.map((t) => t!.id)],
      })
    }
  }

  for (const e of graph.edges) {
    if (e.type !== 'REFINANCES') continue
    const pp = nodeById.get(e.source)
    const loan = nodeById.get(e.target)
    if (pp?.type !== 'policy_product' || loan?.type !== 'loan') continue
    const saving = Math.round((loan.principal * (loan.rate - pp.rate)) / 100 / 12)
    const feeClause = graph.nodes.find((c) => c.type === 'clause' && c.contractId === loan.contractId && c.clauseType === 'prepayment_fee')
    const feeRate = feeClause?.type === 'clause' ? Number(feeClause.params?.rate ?? 0) : 0
    const fee = Math.round(loan.principal * feeRate)
    out.push({
      id: e.id,
      title: `${loan.label} 대환 검토`,
      body: `${pp.label}(연 ${pp.rate}%)로 갈아타면 이자가 월 약 ${won(saving)} 줄 수 있습니다. ` +
        (fee ? `중도상환수수료 ${won(fee)}가 들어 약 ${Math.ceil(fee / saving)}개월이면 회수됩니다. ` : '') + '자격·한도 확인이 필요한 비교 정보입니다.',
      nodes: [pp.id, loan.id, ...(feeClause ? [feeClause.id, loan.contractId] : [])],
    })
  }
  return out
}
