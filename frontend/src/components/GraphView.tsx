import { useEffect, useRef, useState } from 'react'
import cytoscape from 'cytoscape'
import { graph } from '../data/financeGraph.ts'
import { groupOf, nodeSub, type Group } from '../graph/describe.ts'
import { AX, AY, RING, radialLayout, sectorsOf, SIZE, type Sector } from '../graph/layout.ts'
import type { Status } from '../graph/propagate.ts'

export interface NodeMark { status: Status; hop: number }
export interface EdgeMark { status: 'risk' | 'good'; hop: number }
interface Props {
  visible: Set<Group>
  showLabels: boolean
  nodeMarks: Map<string, NodeMark>
  edgeMarks: Map<string, EdgeMark>
  replayKey: number
  selectedId: string | null
  onSelect: (id: string | null) => void
}
const NODE_CLASSES = 'at_risk triggered improved changed'
const HOP_MS = 520 // 홉마다 켜지는 간격
const reducedMotion = () => typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches

// 색뿐 아니라 모양으로도 구분한다. 금액 노드(정산·매입 대금·고정비)는 어느 섹터에서나 팔각형이고,
// 나머지는 섹터(왼쪽=수입, 오른쪽=지출, 위=카드, 아래=대출·계약)마다 모양이 다르다.
const AMOUNT = new Set(['settlement', 'payable', 'fixed_cost'])
const BY_SECTOR: Record<Sector, Partial<Record<string, string>>> = {
  left: { partner: 'ellipse', contract: 'rectangle', clause: 'diamond', signal: 'star' },
  right: { partner: 'round-heptagon', contract: 'cut-rectangle', clause: 'round-triangle', signal: 'star' },
  top: { card: 'round-tag' },
  bottom: { loan: 'hexagon', contract: 'barrel', policy_product: 'round-pentagon', clause: 'pentagon', signal: 'star' },
}
const sectors = sectorsOf(graph)
const shapeOf = (type: string, sector: Sector) => (AMOUNT.has(type) ? 'octagon' : type === 'account' ? 'round-rectangle' : (BY_SECTOR[sector][type] ?? 'round-rectangle'))
const SMALL = new Set(['clause', 'signal'])
const positions = radialLayout(graph)

// 레이더 고리: 동심원 배치의 반지름과 같다. 가게 계좌에서 몇 단계 떨어진 연결인지 읽게 해 준다(설명은 EdgeLegend).
const RADAR: { r: number; label: string }[] = [
  { r: RING[1], label: '1단계 · 돈이 오가는 일정' },
  { r: RING[2], label: '2단계 · 거래 상대' },
  { r: RING[3], label: '3단계 · 계약·근거' },
]

export default function GraphView({ visible, showLabels, nodeMarks, edgeMarks, replayKey, selectedId, onSelect }: Props) {
  const host = useRef<HTMLDivElement>(null)
  const cy = useRef<cytoscape.Core | null>(null)
  const onSelectRef = useRef(onSelect)
  onSelectRef.current = onSelect
  const [view, setView] = useState({ x: 0, y: 0, zoom: 1 }) // 레이더를 지도와 같이 움직이기 위한 pan·zoom
  const pinging = nodeMarks.size > 0

  useEffect(() => {
    const css = getComputedStyle(document.documentElement)
    const v = (n: string) => css.getPropertyValue(n).trim()
    const PURPLE = '#8a63d2'
    const BLUE = '#3b82c4'
    const etype = (t: string[], color: string, extra: cytoscape.Css.Edge = {}) => ({ selector: t.map((x) => `edge[etype="${x}"]`).join(', '), style: { 'line-color': color, 'target-arrow-color': color, ...extra } })
    cy.current = cytoscape({
      container: host.current,
      elements: [
        ...graph.nodes.map((n) => ({
          data: { id: n.id, type: n.type, shape: shapeOf(n.type, sectors[n.id]), w: SIZE[n.type].w, h: SIZE[n.type].h, group: groupOf(n.type) ?? 'none', small: SMALL.has(n.type) ? 1 : 0, label: SMALL.has(n.type) ? n.label : [n.label, nodeSub(n)].filter(Boolean).join('\n') },
          position: positions[n.id],
        })),
        ...graph.edges.map((e) => ({ data: { id: e.id, source: e.source, target: e.target, etype: e.type, label: e.label } })),
      ],
      layout: { name: 'preset' },
      minZoom: 0.2,
      maxZoom: 2.4,
      wheelSensitivity: 0.25,
      style: [
        { selector: 'node', style: {
          label: 'data(label)', 'font-size': 12, color: v('--ink'), 'text-valign': 'center', 'text-halign': 'center', 'text-wrap': 'wrap', 'text-max-width': '124px',
          shape: 'data(shape)' as unknown as cytoscape.Css.Node['shape'], width: 'data(w)', height: 'data(h)',
          'background-color': v('--widget'), 'border-width': 2, 'border-color': v('--rule'), 'line-height': 1.2,
          'transition-property': 'background-color, border-color, border-width', 'transition-duration': reducedMotion() ? 0 : 300 } },
        { selector: 'node[type="account"]', style: { 'border-color': v('--ink'), 'border-width': 3.5, 'font-weight': 700, 'background-color': v('--surface') } },
        { selector: 'node[type="partner"]', style: { 'border-color': v('--brand'), 'background-color': v('--brand-bg') } },
        { selector: 'node[type="settlement"], node[type="payable"], node[type="fixed_cost"]', style: { 'border-color': v('--muted'), 'background-color': v('--widget') } },
        { selector: 'node[type="card"]', style: { 'border-color': v('--green'), 'background-color': v('--green-bg') } },
        { selector: 'node[type="loan"]', style: { 'border-color': v('--yellow'), 'background-color': v('--yellow-bg') } },
        { selector: 'node[type="contract"]', style: { 'border-style': 'dashed', 'border-color': v('--muted'), 'background-color': v('--surface') } },
        { selector: 'node[type="policy_product"]', style: { 'border-style': 'dashed', 'border-color': v('--brand'), 'background-color': v('--surface') } },
        { selector: 'node[small = 1]', style: { 'text-valign': 'bottom', 'text-margin-y': 6, 'font-size': 10.5, 'text-max-width': '120px', 'border-width': 2 } },
        { selector: 'node[type="clause"]', style: { 'border-color': PURPLE, 'background-color': v('--surface') } },
        { selector: 'node[type="signal"]', style: { 'border-color': BLUE, 'background-color': v('--surface') } },

        { selector: 'edge', style: { width: 1.8, 'curve-style': 'bezier', 'target-arrow-shape': 'triangle', 'arrow-scale': 0.9, 'line-color': v('--rule'), 'target-arrow-color': v('--rule'),
          'transition-property': 'line-color, target-arrow-color, width', 'transition-duration': reducedMotion() ? 0 : 300,
          label: '', 'font-size': 10.5, color: v('--muted'), 'text-background-color': v('--bg'), 'text-background-opacity': 0.9, 'text-background-padding': '2px', 'text-rotation': 'autorotate' } },
        // 돈이 실제로 움직이는 엣지는 실선, 조건·규칙 관계는 점선, 신호는 얇은 점선
        etype(['SETTLES', 'DEPOSITS_TO', 'FUNDS', 'PAYS_TO', 'CHARGED_TO'], v('--muted'), { 'line-style': 'solid', width: 2.4 }),
        etype(['PAID_WITH'], v('--green'), { 'line-style': 'dashed', width: 2 }),
        etype(['GOVERNED_BY', 'HAS_CLAUSE'], v('--muted'), { 'line-style': 'dotted', width: 1.6 }),
        etype(['BENEFIT_APPLIES'], v('--green'), { 'line-style': 'dotted', width: 2.2 }),
        etype(['CROSS_TRIGGERS'], PURPLE, { 'line-style': 'dotted', width: 2.4 }),
        etype(['REFINANCES'], v('--yellow'), { 'line-style': 'dotted', width: 2.4 }),
        etype(['SIGNALS'], BLUE, { 'line-style': 'dotted', width: 1 }),
        // 엣지 라벨은 hover·선택·위험 경로일 때(또는 "항상 표시"를 켰을 때)만 보인다
        { selector: 'edge.lab, edge.hov, edge.nb, edge.risk', style: { label: 'data(label)' } },
        { selector: 'edge.hov', style: { width: 3.2 } },
        { selector: '.hidden', style: { display: 'none' } },
        { selector: '.dim', style: { opacity: 0.16 } },
        // 시나리오 결과: 위험(at_risk)·발동(triggered)은 빨강, 개선은 초록, 변경은 청록
        { selector: 'node.at_risk', style: { 'border-color': v('--red'), 'background-color': v('--red-bg'), 'border-width': 3.5 } },
        { selector: 'node.triggered', style: { 'border-color': v('--red'), 'background-color': v('--red-bg'), 'border-width': 6 } },
        { selector: 'node.improved', style: { 'border-color': v('--green'), 'background-color': v('--green-bg'), 'border-width': 4 } },
        { selector: 'node.changed', style: { 'border-color': v('--brand'), 'background-color': v('--brand-bg'), 'border-width': 3.5 } },
        { selector: 'edge.risk', style: { 'line-color': v('--red'), 'target-arrow-color': v('--red'), width: 4.5, 'line-style': 'solid' } },
        { selector: 'edge.good', style: { 'line-color': v('--green'), 'target-arrow-color': v('--green'), width: 4.5, 'line-style': 'solid' } },
        { selector: 'node.sel', style: { 'border-width': 4, 'border-color': v('--brand') } },
      ],
    })
    const sync = () => { const c = cy.current!; setView({ ...c.pan(), zoom: c.zoom() }) }
    cy.current.on('viewport', sync)
    cy.current.fit(undefined, 24)
    sync()
    cy.current.on('mouseover', 'edge', (e) => e.target.addClass('hov'))
    cy.current.on('mouseout', 'edge', (e) => e.target.removeClass('hov'))
    cy.current.on('tap', 'node', (e) => onSelectRef.current(e.target.id()))
    cy.current.on('tap', (e) => { if (e.target === cy.current) onSelectRef.current(null) })
    return () => cy.current?.destroy()
  }, [])

  // 그룹 필터: 사업용 계좌(group 'none')는 항상 보인다
  useEffect(() => {
    const c = cy.current
    if (!c) return
    c.nodes().forEach((n) => { const g = n.data('group') as string; n.toggleClass('hidden', g !== 'none' && !visible.has(g as Group)) })
    c.fit(c.elements(':visible'), 24)
  }, [visible])

  useEffect(() => {
    cy.current?.edges().toggleClass('lab', showLabels)
  }, [showLabels])

  // 시나리오 결과: 충격 노드부터 홉 순서대로 하나씩 켠다. 모션 줄이기 설정이면 한 번에 표시한다.
  useEffect(() => {
    const c = cy.current
    if (!c) return
    c.elements().removeClass(`${NODE_CLASSES} risk good`)
    const apply = (hop: number | null) => {
      nodeMarks.forEach((m, id) => { if (hop === null || m.hop === hop) c.getElementById(id).addClass(m.status) })
      edgeMarks.forEach((m, id) => { if (hop === null || m.hop === hop) c.getElementById(id).addClass(m.status) })
    }
    if (reducedMotion()) { apply(null); return }
    const maxHop = Math.max(0, ...[...nodeMarks.values()].map((m) => m.hop), ...[...edgeMarks.values()].map((m) => m.hop))
    const timers = Array.from({ length: maxHop + 1 }, (_, h) => window.setTimeout(() => apply(h), h * HOP_MS))
    return () => timers.forEach((t) => window.clearTimeout(t))
  }, [nodeMarks, edgeMarks, replayKey])

  useEffect(() => {
    const c = cy.current
    if (!c) return
    c.elements().removeClass('dim sel nb')
    if (!selectedId) return
    const n = c.getElementById(selectedId)
    if (n.empty()) return
    c.elements().not(n.closedNeighborhood()).addClass('dim')
    n.connectedEdges().addClass('nb')
    n.addClass('sel')
  }, [selectedId])

  const cx = view.x, cyy = view.y, z = view.zoom
  return (
    <div className="radar-host">
      <svg className="radar" aria-hidden>
        <defs>
          <radialGradient id="radar-fade">
            <stop offset="0" stopColor="var(--brand)" stopOpacity="0.07" />
            <stop offset="1" stopColor="var(--brand)" stopOpacity="0" />
          </radialGradient>
        </defs>
        <ellipse cx={cx} cy={cyy} rx={AX * RING[3] * 1.12 * z} ry={AY * RING[3] * 1.12 * z} fill="url(#radar-fade)" />
        <line x1={cx - AX * RING[3] * 1.12 * z} x2={cx + AX * RING[3] * 1.12 * z} y1={cyy} y2={cyy} className="radar-axis" />
        <line x1={cx} x2={cx} y1={cyy - AY * RING[3] * 1.12 * z} y2={cyy + AY * RING[3] * 1.12 * z} className="radar-axis" />
        {RADAR.map((ring) => (
          <g key={ring.r}>
            <ellipse cx={cx} cy={cyy} rx={AX * ring.r * z} ry={AY * ring.r * z} className="radar-ring"><title>{ring.label}</title></ellipse>
          </g>
        ))}
        {pinging && !reducedMotion() && (
          // 시나리오를 실행하면 가게 계좌에서 바깥쪽으로 신호가 한 번 퍼진다
          <ellipse key={replayKey} cx={cx} cy={cyy} className="radar-ping" rx={0} ry={0}>
            <animate attributeName="rx" from="0" to={AX * RING[3] * 1.12 * z} dur="1.6s" fill="freeze" />
            <animate attributeName="ry" from="0" to={AY * RING[3] * 1.12 * z} dur="1.6s" fill="freeze" />
            <animate attributeName="opacity" from="0.55" to="0" dur="1.6s" fill="freeze" />
          </ellipse>
        )}
      </svg>
      <div ref={host} className="cy" role="img" aria-label="금융지도: 사업용 계좌를 중심으로 정산, 지급, 카드, 대출, 계약과 조항, 신호가 연결된 관계도. 바깥 고리로 갈수록 계좌에서 멀리 떨어진 연결이다." />
    </div>
  )
}
