// 내 금융지도 (US-06, T22): GET /api/graph의 노드·관계를 사업장 중심으로 그린다.
// US-08 (T38): path가 있으면 경로 노드를 강조하고 지급에 막히는 순서 번호를 붙이며, 경로 밖 노드는 흐리게 한다.
import { useEffect, useRef, useState } from 'react'
import cytoscape from 'cytoscape'
import { api, type GraphDto, type ImpactPathDto, type PathNodeRef } from '../api.ts'
import { won } from '../data.ts'

const KO: Record<string, string> = { Business: '사업장', Counterparty: '거래처', Contract: '계약', FixedCost: '고정비', Loan: '대출' }
const CONTRACT_KO: Record<string, string> = { SALES: '매출 계약', PURCHASE: '매입 계약', LEASE: '고정비 계약', LOAN: '대출 약정' }
const COLOR: Record<string, string> = { Business: '#2f5bd3', Counterparty: '#7a8aa6', Contract: '#9ca3af', FixedCost: '#d97706', Loan: '#b45309' }
const KEY: Record<string, string> = { Business: 'business_id', Counterparty: 'counterparty_id', Contract: 'contract_id', FixedCost: 'fixed_cost_id', Loan: 'loan_id' }
const CIRCLED = '①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳'

function labelOf(n: GraphDto['nodes'][number]): string {
  const p = n.props as Record<string, string | number>
  if (n.label === 'Contract') return `${CONTRACT_KO[p.contract_type] ?? '계약'}\n${won(Number(p.amount))}`
  if (n.label === 'FixedCost') return `${p.name}\n${won(Number(p.amount))}`
  if (n.label === 'Loan') return `${p.name}\n월 ${won(Number(p.installment))}`
  return String(p.name ?? KO[n.label])
}

/** 경로 단계의 노드 참조(라벨 + 원본 ID)를 그래프 노드 id로 바꾼다. 사업장은 하나뿐이라 ID 없이 찾는다. */
function matcher(g: GraphDto) {
  return (ref: PathNodeRef) => g.nodes.find((n) => n.label === ref.label && (ref.id === undefined || Number(n.props[KEY[ref.label]]) === ref.id))?.id
}

interface Props {
  path?: ImpactPathDto | null
  /** 고른 단계 (steps 인덱스). 그 단계 노드를 더 진하게 표시한다. */
  selected?: number | null
  onSelectStep?: (i: number) => void
}

export default function LiveMap({ path, selected, onSelectStep }: Props) {
  const host = useRef<HTMLDivElement>(null)
  const cyRef = useRef<cytoscape.Core | null>(null)
  const graphRef = useRef<GraphDto | null>(null)
  const pick = useRef(onSelectStep)
  useEffect(() => { pick.current = onSelectStep }, [onSelectStep])
  const [info, setInfo] = useState('')
  const [ready, setReady] = useState(0)
  useEffect(() => {
    let cy: cytoscape.Core | null = null
    api<GraphDto>('/api/graph').then((g) => {
      if (!host.current) return
      if (!g.nodes.length) { setInfo('그래프가 비어 있습니다. 일정을 등록한 뒤 "금융지도 다시 만들기"를 누르세요.'); return }
      setInfo(`노드 ${g.nodes.length}개 · 관계 ${g.edges.length}개`)
      graphRef.current = g
      cy = cytoscape({
        container: host.current,
        elements: [
          ...g.nodes.map((n) => ({ data: { id: n.id, label: labelOf(n), kind: n.label, badge: '' } })),
          ...g.edges.map((e) => ({ data: { id: e.id, source: e.source, target: e.target, label: e.type } })),
        ],
        style: [
          { selector: 'node', style: { label: (el: cytoscape.NodeSingular) => `${el.data('badge')}${el.data('label')}`, 'text-wrap': 'wrap', 'font-size': 11, 'text-valign': 'bottom', 'text-margin-y': 4, width: 26, height: 26, 'background-color': (el: cytoscape.NodeSingular) => COLOR[el.data('kind')] ?? '#999', 'transition-property': 'opacity', 'transition-duration': 200 } },
          { selector: 'node[kind = "Business"]', style: { width: 46, height: 46, 'font-weight': 700 } },
          { selector: 'edge', style: { width: 1.4, 'line-color': '#c8ccd2', 'target-arrow-color': '#c8ccd2', 'target-arrow-shape': 'triangle', 'curve-style': 'bezier', label: 'data(label)', 'font-size': 8, color: '#8a9099' } },
          // US-08 경로 강조 (AC-01·05)
          { selector: '.dim', style: { opacity: 0.18 } },
          { selector: 'node.on-path', style: { 'border-width': 3, 'border-color': '#d64545', 'font-weight': 700, color: '#b42318' } },
          { selector: 'node.cause', style: { 'background-color': '#d64545' } },
          { selector: 'node.shortage', style: { 'border-width': 5, 'border-color': '#d64545' } },
          { selector: 'edge.on-path', style: { width: 3, 'line-color': '#d64545', 'target-arrow-color': '#d64545', color: '#b42318' } },
          { selector: 'node.picked', style: { 'overlay-color': '#d64545', 'overlay-opacity': 0.18, 'overlay-padding': 8 } },
        ],
        layout: { name: 'concentric', concentric: (n: cytoscape.NodeSingular) => ({ Business: 4, Counterparty: 3, FixedCost: 3, Loan: 3, Contract: 2 }[n.data('kind') as string] ?? 1), levelWidth: () => 1, minNodeSpacing: 34 },
      })
      cy.on('tap', 'node.on-path', (ev) => {
        const i = Number(ev.target.data('step'))
        if (!Number.isNaN(i)) pick.current?.(i)
      })
      cyRef.current = cy
      setReady((k) => k + 1)
    }).catch((e) => setInfo(`금융지도를 불러오지 못했습니다: ${e.message}`))
    return () => { cy?.destroy(); cyRef.current = null }
  }, [])

  // 경로가 바뀌면(시나리오 전환, AC-06) 강조를 다시 칠한다
  useEffect(() => {
    const cy = cyRef.current
    const g = graphRef.current
    if (!cy || !g) return
    cy.elements().removeClass('dim on-path cause shortage picked')
    cy.nodes().forEach((n) => { n.data('badge', ''); n.removeData('step') })
    if (!path?.steps.length) return
    const find = matcher(g)
    const onPath = new Set<string>()
    path.steps.forEach((st, i) => {
      for (const ref of st.nodes) {
        const id = find(ref)
        if (!id) continue
        onPath.add(id)
        const n = cy.getElementById(id)
        n.addClass('on-path')
        if (st.role === 'CAUSE') n.addClass('cause')
        if (st.role === 'SHORTAGE') n.addClass('shortage')
        if (n.data('step') === undefined || st.role === 'PAYMENT') n.data('step', i)
        // 번호는 지급이 실제로 나가는 노드(출처)에만 붙인다. 한 노드에 지급이 여러 건이면 번호를 이어 붙인다.
        if (st.role === 'PAYMENT' && st.order && ref === st.nodes[0]) n.data('badge', `${n.data('badge')}${CIRCLED[st.order - 1] ?? `(${st.order})`}`)
        if (i === selected) n.addClass('picked')
      }
    })
    cy.nodes().forEach((n) => { if (!onPath.has(n.id())) n.addClass('dim') })
    cy.edges().forEach((e) => {
      if (onPath.has(e.source().id()) && onPath.has(e.target().id())) e.addClass('on-path')
      else e.addClass('dim')
    })
    cy.nodes('.on-path').forEach((n) => { if (n.data('badge')) n.data('badge', `${n.data('badge')} `) })
  }, [path, selected, ready])

  return (
    <div>
      <p className="muted small" style={{ marginBottom: 8 }}>{info}</p>
      <div ref={host} className="live-map" role="img" aria-label="사업장 중심 금융지도" />
    </div>
  )
}
