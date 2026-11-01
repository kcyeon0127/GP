// 동심원(radial) 레이아웃: 사업용 계좌가 중심.
//   ring 1: 현금흐름 이벤트(정산, 매입 대금, 고정비, 대출 상환)   ring 2: 주체(거래처, 카드)
//   ring 3: 근거(계약서, 정책 상품, 신호)                          ring 4: 조항(계약서 바깥에 붙임)
// 각도 섹터: 왼쪽 = 수입, 오른쪽 = 지출, 아래 = 대출·계약, 위 = 카드. 대출은 상환 이벤트를 겸하므로 ring 1에 둔다.
import type { FinanceGraph, GraphNode, NodeType } from '../data/financeGraph.ts'

export interface Size { w: number; h: number }
export const SIZE: Record<NodeType, Size> = {
  account: { w: 160, h: 66 }, partner: { w: 108, h: 58 }, settlement: { w: 152, h: 58 }, payable: { w: 152, h: 58 },
  fixed_cost: { w: 152, h: 58 }, loan: { w: 168, h: 72 }, card: { w: 144, h: 54 }, contract: { w: 150, h: 52 },
  clause: { w: 30, h: 30 }, policy_product: { w: 176, h: 84 }, signal: { w: 34, h: 34 },
}

export type Sector = 'left' | 'right' | 'top' | 'bottom'
// from → to 방향으로 목록 순서대로 배치한다(화면 좌표: 0°=오른쪽, 90°=아래).
const SECTOR: Record<Sector, { from: number; to: number }> = {
  left: { from: 222, to: 138 },
  right: { from: -42, to: 42 },
  top: { from: 232, to: 308 },
  bottom: { from: 132, to: 48 },
}
export const RING = { 1: 210, 2: 390, 3: 570 }
export const AX = 1.3 // 한 화면에 맞추기 위한 타원 비율
export const AY = 0.9

const RING1: Record<Sector, string[]> = { left: ['S1', 'S2', 'S3'], right: ['Y1', 'Y2', 'F1', 'F2', 'F3'], top: [], bottom: ['L1', 'L2'] }
const RING2_TOP = ['C1', 'C2']
// 같은 각도 근처에 모이는 ring 3 노드: [앵커 노드, 각도 오프셋]
const RING3: Record<string, [string, number]> = {
  K_SALES: ['S1', -7], SG1: ['S1', 13],
  K_LEASE: ['F1', 4], K_SUP: ['Y1', 12],
  K_L1: ['L1', 0], PP1: ['L1', 22], SG2: ['L1', 38],
  K_L2: ['L2', -4],
}

const rad = (deg: number) => (deg * Math.PI) / 180
const polar = (deg: number, r: number) => ({ x: AX * r * Math.cos(rad(deg)), y: AY * r * Math.sin(rad(deg)) })

export type Positions = Record<string, { x: number; y: number }>

// 노드가 속한 섹터(왼쪽=수입, 오른쪽=지출, 위=카드, 아래=대출·계약). 도형을 섹터별로 달리하는 데 쓴다.
export function sectorsOf(graph: FinanceGraph): Record<string, Sector> {
  const s: Record<string, Sector> = { ACC: 'bottom' }
  ;(Object.keys(RING1) as Sector[]).forEach((sec) => RING1[sec].forEach((id) => { s[id] = sec }))
  RING2_TOP.forEach((id) => { s[id] = 'top' })
  for (const [id, [anchor]] of Object.entries(RING3)) s[id] = s[anchor]
  graph.nodes.forEach((n) => {
    if (n.type === 'partner') {
      const own = graph.nodes.find((m) => (m.type === 'settlement' || m.type === 'payable') && m.partnerId === n.id)
      if (own) s[n.id] = s[own.id]
    }
  })
  graph.nodes.forEach((n) => { if (n.type === 'clause') s[n.id] = s[n.contractId] })
  return s
}

export function radialLayout(graph: FinanceGraph): Positions {
  const pos: Positions = { ACC: { x: 0, y: 0 } }
  const angle: Record<string, number> = {}
  const place = (id: string, deg: number, ring: 1 | 2 | 3) => {
    angle[id] = deg
    pos[id] = polar(deg, RING[ring])
  }

  // ring 1
  for (const sector of Object.keys(RING1) as Sector[]) {
    const ids = RING1[sector]
    const { from, to } = SECTOR[sector]
    ids.forEach((id, i) => place(id, from + ((i + 0.5) * (to - from)) / ids.length, 1))
  }
  // ring 2: 거래처는 연결된 정산·지급과 같은 각도, 카드는 위쪽
  for (const n of graph.nodes) {
    if (n.type === 'partner') {
      const own = graph.nodes.filter((m) => (m.type === 'settlement' || m.type === 'payable') && m.partnerId === n.id)
      place(n.id, own.reduce((a, m) => a + angle[m.id], 0) / own.length, 2)
    }
  }
  const { from: tf, to: tt } = SECTOR.top
  RING2_TOP.forEach((id, i) => place(id, tf + ((i + 0.5) * (tt - tf)) / RING2_TOP.length, 2))
  // ring 3
  for (const [id, [anchor, off]] of Object.entries(RING3)) place(id, angle[anchor] + off, 3)
  // ring 4: 조항은 소속 계약서 바깥쪽에 계약서 둘레를 따라 펼친다
  const byContract = new Map<string, GraphNode[]>()
  graph.nodes.forEach((n) => { if (n.type === 'clause') byContract.set(n.contractId, [...(byContract.get(n.contractId) ?? []), n]) })
  for (const [cid, list] of byContract) {
    const c = pos[cid]
    const len = Math.hypot(c.x, c.y) || 1
    const ux = c.x / len, uy = c.y / len
    const tx = -uy, ty = ux
    list.forEach((n, i) => {
      const t = (i - (list.length - 1) / 2) * 70
      pos[n.id] = { x: c.x + ux * 100 + tx * t, y: c.y + uy * 80 + ty * t }
    })
  }

  relax(graph, pos)
  return pos
}

// 겹치는 노드를 서로 밀어낸다(사업용 계좌는 고정).
function relax(graph: FinanceGraph, pos: Positions) {
  const ids = graph.nodes.map((n) => n.id)
  const type = new Map(graph.nodes.map((n) => [n.id, n.type]))
  const gap = 16
  for (let it = 0; it < 80; it++) {
    let moved = false
    for (let i = 0; i < ids.length; i++) {
      for (let j = i + 1; j < ids.length; j++) {
        const a = ids[i], b = ids[j]
        const sa = SIZE[type.get(a)!], sb = SIZE[type.get(b)!]
        const dx = pos[b].x - pos[a].x, dy = pos[b].y - pos[a].y
        const ox = (sa.w + sb.w) / 2 + gap - Math.abs(dx)
        const oy = (sa.h + sb.h) / 2 + gap - Math.abs(dy)
        if (ox <= 0 || oy <= 0) continue
        moved = true
        const fixA = a === 'ACC', fixB = b === 'ACC'
        const wa = fixA ? 0 : fixB ? 1 : 0.5, wb = fixB ? 0 : fixA ? 1 : 0.5
        if (oy < ox) {
          const s = dy >= 0 ? 1 : -1
          pos[a].y -= s * oy * wa; pos[b].y += s * oy * wb
        } else {
          const s = dx >= 0 ? 1 : -1
          pos[a].x -= s * ox * wa; pos[b].x += s * ox * wb
        }
      }
    }
    if (!moved) break
  }
}
