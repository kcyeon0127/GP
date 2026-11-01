// 내 금융지도 (US-06, T22): GET /api/graph의 노드·관계를 사업장 중심으로 그린다.
import { useEffect, useRef, useState } from 'react'
import cytoscape from 'cytoscape'
import { api, type GraphDto } from '../api.ts'
import { won } from '../data.ts'

const KO: Record<string, string> = { Business: '사업장', Counterparty: '거래처', Contract: '계약', FixedCost: '고정비', Loan: '대출' }
const CONTRACT_KO: Record<string, string> = { SALES: '매출 계약', PURCHASE: '매입 계약', LEASE: '고정비 계약', LOAN: '대출 약정' }
const COLOR: Record<string, string> = { Business: '#2f5bd3', Counterparty: '#7a8aa6', Contract: '#9ca3af', FixedCost: '#d97706', Loan: '#b45309' }

function labelOf(n: GraphDto['nodes'][number]): string {
  const p = n.props as Record<string, string | number>
  if (n.label === 'Contract') return `${CONTRACT_KO[p.contract_type] ?? '계약'}\n${won(Number(p.amount))}`
  if (n.label === 'FixedCost') return `${p.name}\n${won(Number(p.amount))}`
  if (n.label === 'Loan') return `${p.name}\n월 ${won(Number(p.installment))}`
  return String(p.name ?? KO[n.label])
}

export default function LiveMap() {
  const host = useRef<HTMLDivElement>(null)
  const [info, setInfo] = useState('')
  useEffect(() => {
    let cy: cytoscape.Core | null = null
    api<GraphDto>('/api/graph').then((g) => {
      if (!host.current) return
      if (!g.nodes.length) { setInfo('그래프가 비어 있습니다. 일정을 등록한 뒤 "금융지도 다시 만들기"를 누르세요.'); return }
      setInfo(`노드 ${g.nodes.length}개 · 관계 ${g.edges.length}개`)
      cy = cytoscape({
        container: host.current,
        elements: [
          ...g.nodes.map((n) => ({ data: { id: n.id, label: labelOf(n), kind: n.label } })),
          ...g.edges.map((e) => ({ data: { id: e.id, source: e.source, target: e.target, label: e.type } })),
        ],
        style: [
          { selector: 'node', style: { label: 'data(label)', 'text-wrap': 'wrap', 'font-size': 11, 'text-valign': 'bottom', 'text-margin-y': 4, width: 26, height: 26, 'background-color': (el: cytoscape.NodeSingular) => COLOR[el.data('kind')] ?? '#999' } },
          { selector: 'node[kind = "Business"]', style: { width: 46, height: 46, 'font-weight': 700 } },
          { selector: 'edge', style: { width: 1.4, 'line-color': '#c8ccd2', 'target-arrow-color': '#c8ccd2', 'target-arrow-shape': 'triangle', 'curve-style': 'bezier', label: 'data(label)', 'font-size': 8, color: '#8a9099' } },
        ],
        layout: { name: 'concentric', concentric: (n: cytoscape.NodeSingular) => ({ Business: 4, Counterparty: 3, FixedCost: 3, Loan: 3, Contract: 2 }[n.data('kind') as string] ?? 1), levelWidth: () => 1, minNodeSpacing: 34 },
      })
    }).catch((e) => setInfo(`금융지도를 불러오지 못했습니다: ${e.message}`))
    return () => cy?.destroy()
  }, [])
  return (
    <>
      <p className="muted small" style={{ marginBottom: 8 }}>{info}</p>
      <div ref={host} className="live-map" role="img" aria-label="사업장 중심 금융지도" />
    </>
  )
}
