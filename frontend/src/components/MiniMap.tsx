import { Link } from 'react-router-dom'
import { won } from '../data.ts'
import { graph } from '../data/financeGraph.ts'

// 홈 화면용 요약 금융지도: 노드 34개를 큰 묶음 6개로 줄여서 보여준다. 숫자는 전부 그래프 데이터에서 합산한다.
// 전체 지도와 같은 모양·색을 써서 같은 지도로 읽히게 하고, 카드 전체를 누르면 금융지도로 이동한다.
type Kind = 'account' | 'rev' | 'out' | 'card' | 'loan' | 'contract'
interface Box { id: Kind; kind: Kind; x: number; y: number; w: number; h: number; title: string; sub: string }

const sum = (xs: number[]) => xs.reduce((a, b) => a + b, 0)

export type MiniStats = ReturnType<typeof summary>

function summary() {
  const n = graph.nodes
  const settle = n.filter((x) => x.type === 'settlement')
  const outs = n.filter((x) => x.type === 'payable' || x.type === 'fixed_cost')
  const loans = n.filter((x) => x.type === 'loan')
  const cards = n.filter((x) => x.type === 'card')
  const contracts = n.filter((x) => x.type === 'contract')
  const clauses = n.filter((x) => x.type === 'clause')
  const acc = n.find((x) => x.type === 'account')
  const inAmt = sum(settle.map((x) => (x.type === 'settlement' ? x.amount : 0)))
  const outAmt = sum(outs.map((x) => (x.type === 'payable' || x.type === 'fixed_cost' ? x.amount : 0)))
  const loanAmt = sum(loans.map((x) => (x.type === 'loan' ? x.nextPaymentAmount : 0)))
  return {
    balance: acc?.type === 'account' ? acc.balance : 0, inAmt, outAmt, loanAmt,
    partners: n.filter((x) => x.type === 'partner' && x.role === 'sales').length,
    outCount: outs.length, loans: loans.length, cards: cards.length, contracts: contracts.length, clauses: clauses.length,
  }
}

const COLOR: Record<Kind, { stroke: string; fill: string; dash?: string }> = {
  account: { stroke: 'var(--ink)', fill: 'var(--surface)' },
  rev: { stroke: 'var(--brand)', fill: 'var(--brand-bg)' },
  out: { stroke: 'var(--muted)', fill: 'var(--widget)' },
  card: { stroke: 'var(--green)', fill: 'var(--green-bg)' },
  loan: { stroke: 'var(--yellow)', fill: 'var(--yellow-bg)' },
  contract: { stroke: 'var(--muted)', fill: 'var(--surface)', dash: '5 4' },
}

function Shape({ b }: { b: Box }) {
  const c = COLOR[b.kind]
  const { x, y, w, h } = b
  const common = { fill: c.fill, stroke: c.stroke, strokeWidth: b.kind === 'account' ? 3 : 2, strokeDasharray: c.dash }
  const l = x - w / 2, r = x + w / 2, t = y - h / 2, bt = y + h / 2
  switch (b.kind) {
    case 'rev': return <ellipse cx={x} cy={y} rx={w / 2} ry={h / 2} {...common} />
    case 'out': { const k = 16; return <polygon points={`${l + k},${t} ${r - k},${t} ${r},${t + k} ${r},${bt - k} ${r - k},${bt} ${l + k},${bt} ${l},${bt - k} ${l},${t + k}`} {...common} /> } // 금액 = 팔각형
    case 'loan': { const k = 18; return <polygon points={`${l + k},${t} ${r - k},${t} ${r},${y} ${r - k},${bt} ${l + k},${bt} ${l},${y}`} {...common} /> }
    case 'card': { const k = 16; return <polygon points={`${l},${t} ${r - k},${t} ${r},${y} ${r - k},${bt} ${l},${bt}`} {...common} /> }
    default: return <rect x={l} y={t} width={w} height={h} rx={12} {...common} />
  }
}

/** stats를 주면 그 숫자로 그린다(서버 등록 데이터). 없으면 시연 그래프에서 합산한다. */
export default function MiniMap({ stats }: { stats?: MiniStats }) {
  const s = stats ?? summary()
  const boxes: Record<Kind, Box> = {
    account: { id: 'account', kind: 'account', x: 240, y: 160, w: 150, h: 62, title: '사업용 계좌', sub: `잔액 ${won(s.balance)}` },
    rev: { id: 'rev', kind: 'rev', x: 64, y: 160, w: 112, h: 72, title: `매출처 ${s.partners}곳`, sub: `정산 ${won(s.inAmt)}` },
    out: { id: 'out', kind: 'out', x: 416, y: 160, w: 128, h: 80, title: `지출 ${s.outCount}건`, sub: won(s.outAmt) },
    card: { id: 'card', kind: 'card', x: 240, y: 44, w: 140, h: 52, title: `카드 ${s.cards}장`, sub: '매월 청구' },
    loan: { id: 'loan', kind: 'loan', x: 130, y: 280, w: 140, h: 62, title: `대출 ${s.loans}건`, sub: `월 ${won(s.loanAmt)}` },
    contract: { id: 'contract', kind: 'contract', x: 350, y: 280, w: 136, h: 56, title: `계약 ${s.contracts}건`, sub: `조항 ${s.clauses}개` },
  }
  // 돈이 움직이는 연결은 실선, 조건·규칙 연결은 점선. at = 선 위 라벨 위치(노드 사이 빈 곳)
  const links: { from: Kind; to: Kind; label: string; dotted?: boolean; at?: number; dy?: number }[] = [
    { from: 'rev', to: 'account', label: '입금', at: 0.45 },
    { from: 'account', to: 'out', label: '출금', at: 0.53 },
    { from: 'card', to: 'account', label: '카드 청구' },
    { from: 'account', to: 'loan', label: '상환' },
    { from: 'contract', to: 'loan', label: '조항', dotted: true },
    { from: 'contract', to: 'out', label: '계약 근거', dotted: true },
    { from: 'card', to: 'out', label: '혜택', dotted: true },
  ]

  return (
    <Link to="/map" className="minimap" aria-label="금융지도 열기: 계좌·카드·대출·계약의 관계를 한눈에 보는 요약 지도">
      <div className="mm-head">
        <h2>금융지도</h2>
        <span className="mm-go">전체 지도 열기 →</span>
      </div>
      <p className="sub">계좌 중심으로 돈과 계약의 연결을 요약했어요.</p>
      <svg viewBox="0 0 480 322" role="img" aria-label="요약 금융지도" width="100%">
        {links.map((l) => {
          const a = boxes[l.from], b = boxes[l.to]
          const t = l.at ?? 0.5
          const mx = a.x + (b.x - a.x) * t, my = a.y + (b.y - a.y) * t + (l.dy ?? 0)
          const ang = (Math.atan2(b.y - a.y, b.x - a.x) * 180) / Math.PI
          const ax = a.x + (b.x - a.x) * 0.66, ay = a.y + (b.y - a.y) * 0.66
          return (
            <g key={`${l.from}-${l.to}`}>
              <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke={l.dotted ? 'var(--muted)' : 'var(--muted)'} strokeWidth={l.dotted ? 1.8 : 2.6} strokeDasharray={l.dotted ? '1.5 5' : undefined} strokeLinecap="round" />
              <polygon points="0,-5 10,0 0,5" transform={`translate(${ax},${ay}) rotate(${ang})`} fill="var(--muted)" />
              <text x={mx} y={my - 6} textAnchor="middle" className="mm-edge">{l.label}</text>
            </g>
          )
        })}
        {(Object.values(boxes)).map((b) => (
          <g key={b.id}>
            <Shape b={b} />
            <text x={b.x} y={b.y - 3} textAnchor="middle" className="mm-title">{b.title}</text>
            <text x={b.x} y={b.y + 15} textAnchor="middle" className="mm-sub">{b.sub}</text>
          </g>
        ))}
      </svg>
    </Link>
  )
}
