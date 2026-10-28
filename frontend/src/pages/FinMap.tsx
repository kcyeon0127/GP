import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import GraphView, { type EdgeMark, type NodeMark } from '../components/GraphView.tsx'
import Legend from '../components/Legend.tsx'
import { dayLabel, won } from '../data.ts'
import { isRisk } from '../demo.ts'
import { graph, nodeById, type GraphNode } from '../data/financeGraph.ts'
import { EDGE_LABEL, GROUPS, TYPE_LABEL, groupOf, md, nodeLines, nodeSub, type Group } from '../graph/describe.ts'
import { opportunities } from '../graph/opportunities.ts'
import { propagate, type GraphShock, type PropagationResult, type Status } from '../graph/propagate.ts'
import { benefitStatus, clausesOf, reach, scenarioFor, SCENARIO_LABEL, type ScenarioKind } from '../graph/query.ts'

const DEFAULT_VISIBLE = new Set<Group>(['cashflow', 'partner', 'card', 'loanContract']) // 조항·신호는 처음엔 꺼 둔다
const OPPS = opportunities()
const KINDS = Object.keys(SCENARIO_LABEL) as ScenarioKind[]
const partnersAll = graph.nodes.filter((n) => n.type === 'partner')
const loans = graph.nodes.filter((n) => n.type === 'loan')
const payTargets = graph.nodes.filter((n) => n.type === 'payable' || n.type === 'fixed_cost')
const cards = graph.nodes.filter((n) => n.type === 'card')
const STATUS_LABEL: Record<Status, string> = { at_risk: '위험', triggered: '발동', improved: '개선', changed: '변경' }

interface Scn { kind: ScenarioKind | 'none'; partnerId: string; days: number; loanId: string; payId: string; cardId: string; spendUnmet: boolean; pp: number; pct: number }

function shockOf(c: Scn): GraphShock | null {
  switch (c.kind) {
    case 'settlement_delay': return c.partnerId ? { type: 'settlement_delay', partnerId: c.partnerId, days: c.days } : null
    case 'partner_closure': return c.partnerId ? { type: 'partner_closure', partnerId: c.partnerId } : null
    case 'loan_default': return c.loanId ? { type: 'loan_default', loanId: c.loanId } : null
    case 'payment_switch': return c.payId && c.cardId ? { type: 'payment_switch', targetId: c.payId, cardId: c.cardId, prevMonthSpend: c.spendUnmet ? 0 : undefined } : null
    case 'rate_up': return { type: 'rate_up', pp: c.pp }
    case 'revenue_drop': return { type: 'revenue_drop', pct: c.pct }
    case 'current': return { type: 'current' }
    default: return null
  }
}

function describe(sh: GraphShock): string {
  const label = (id: string) => nodeById.get(id)?.label ?? id
  switch (sh.type) {
    case 'settlement_delay': { const p = nodeById.get(sh.partnerId); return p?.type === 'partner' && p.role === 'purchase' ? `${p.label} 대금 ${sh.days}일 지급 지연` : `${label(sh.partnerId)} 정산 ${sh.days}일 지연` }
    case 'partner_closure': return `${label(sh.partnerId)} 폐업`
    case 'loan_default': return `${label(sh.loanId)} 연체`
    case 'payment_switch': return `${label(sh.targetId)}을(를) ${label(sh.cardId)}로 결제`
    case 'rate_up': return `변동금리 +${sh.pp}%p`
    case 'revenue_drop': return `매출 ${sh.pct}% 하락`
    case 'current': return '현재 상황: 이미 벌어진 일이 번지는 길'
    case 'refinance': return `${label(sh.loanId)} 대환`
  }
}

export default function FinMap() {
  // 링크로 상태를 공유할 수 있다: /map?node=L1  /map?partner=P1&days=14
  const q = new URLSearchParams(window.location.search)
  const [selected, setSelected] = useState<string | null>(() => (nodeById.has(q.get('node') ?? '') ? q.get('node') : null))
  const [visible, setVisible] = useState<Set<Group>>(DEFAULT_VISIBLE)
  const [alwaysLabels, setAlwaysLabels] = useState(false)
  const [scn, setScn] = useState<Scn>(() => {
    // 예: ?partner=P1&days=14 · ?scenario=loan_default&loan=L1 · ?scenario=payment_switch&pay=Y1&card=C1&unmet=1 · ?scenario=rate_up&pp=1
    const pid = q.get('partner')
    const partnerOk = partnersAll.some((p) => p.id === pid)
    const asked = q.get('scenario') as ScenarioKind | null
    const idOr = (v: string | null, list: GraphNode[], d: string) => (list.some((n) => n.id === v) ? (v as string) : d)
    return {
      kind: asked && KINDS.includes(asked) ? asked : partnerOk ? 'settlement_delay' : isRisk ? 'current' : 'none',
      partnerId: partnerOk ? (pid as string) : '',
      days: Math.min(45, Math.max(1, Number(q.get('days')) || 14)),
      loanId: idOr(q.get('loan'), loans, 'L1'), payId: idOr(q.get('pay'), payTargets, 'Y1'), cardId: idOr(q.get('card'), cards, 'C1'),
      spendUnmet: q.get('unmet') === '1', pp: Math.min(3, Math.max(0.5, Number(q.get('pp')) || 1)),
      pct: Math.min(60, Math.max(5, Number(q.get('pct')) || 20)),
    }
  })
  const [focus, setFocus] = useState<string[] | null>(null)
  const [oppOpen, setOppOpen] = useState(false)
  const patch = (p: Partial<Scn>) => { setScn((c) => ({ ...c, ...p })); setFocus(null) }

  const shock = useMemo(() => shockOf(scn), [scn])
  const result: PropagationResult | null = useMemo(() => (shock ? propagate(graph, shock) : null), [shock])

  const [replay, setReplay] = useState(0)
  const nodeMarks = useMemo(() => {
    const m = new Map<string, NodeMark>()
    result?.nodes.forEach((v, id) => m.set(id, { status: v.status, hop: v.hop }))
    if (!result) focus?.forEach((id) => m.set(id, { status: 'changed', hop: 0 }))
    return m
  }, [result, focus])
  const edgeMarks = useMemo(() => {
    const m = new Map<string, EdgeMark>()
    result?.edges.forEach((hop, id) => {
      const e = graph.edges.find((x) => x.id === id)
      if (!e) return
      const bad = (n: string) => { const s = result.nodes.get(n)?.status; return s === 'at_risk' || s === 'triggered' }
      m.set(id, { status: bad(e.source) || bad(e.target) ? 'risk' : 'good', hop })
    })
    return m
  }, [result])
  const counts = useMemo(() => {
    const c: Record<Status, number> = { at_risk: 0, triggered: 0, improved: 0, changed: 0 }
    result?.nodes.forEach((v) => { c[v.status] += 1 })
    return c
  }, [result])

  // 강조할 경로에 조항·신호가 있으면 그 그룹은 꺼져 있어도 보여준다
  const shown = useMemo(() => {
    const s = new Set(visible)
    nodeMarks.forEach((_v, id) => { const n = nodeById.get(id); const g = n && groupOf(n.type); if (g) s.add(g) })
    return s
  }, [visible, nodeMarks])

  const toggle = (g: Group) => setVisible((cur) => {
    const next = new Set(cur)
    if (next.has(g)) next.delete(g)
    else next.add(g)
    return next
  })

  const sel = selected ? nodeById.get(selected) : null
  const down = useMemo(() => (selected ? reach(selected, 'down') : []), [selected])
  const up = useMemo(() => (selected ? reach(selected, 'up') : []), [selected])

  const startScenario = (n: GraphNode) => {
    const s = scenarioFor(n)
    if (!s) return
    const next: Partial<Scn> = { kind: s.kind }
    if (s.kind === 'settlement_delay' || s.kind === 'partner_closure') next.partnerId = s.targetId
    if (s.kind === 'loan_default') next.loanId = s.targetId
    if (s.kind === 'revenue_drop') next.pct = 20
    if (s.kind === 'payment_switch') {
      next.payId = s.targetId
      next.cardId = n.type === 'card' ? n.id : (cards.find((c) => c.type === 'card' && c.benefits.some((b) => b.appliesTo.includes(s.targetId)))?.id ?? 'C1')
    }
    patch(next)
    setOppOpen(false)
  }

  const b = result?.balance
  const delta = b ? b.minP50 - b.baseMinP50 : 0

  return (
    <div className="map-page">
      <div className="page-head" style={{ marginBottom: 10 }}>
        <Link to="/" className="back">← 홈</Link>
        <h1 style={{ fontSize: 22 }}>금융지도</h1>
      </div>

      <div className="map-toolbar">
        <div className="seg" role="group" aria-label="보이는 종류">
          {GROUPS.map((g) => (
            <button key={g.id} className={shown.has(g.id) ? 'on' : ''} aria-pressed={shown.has(g.id)} onClick={() => toggle(g.id)}>{g.label}</button>
          ))}
        </div>
        <div className="scn">
          <b>시나리오</b>
          <select aria-label="시나리오 종류" value={scn.kind} onChange={(e) => patch({ kind: e.target.value as Scn['kind'] })}>
            <option value="none">선택 안 함</option>
            {KINDS.filter((k) => k !== 'current' || isRisk).map((k) => <option key={k} value={k}>{SCENARIO_LABEL[k]}</option>)}
          </select>
          {(scn.kind === 'settlement_delay' || scn.kind === 'partner_closure') && (
            <select aria-label="거래처" value={scn.partnerId} onChange={(e) => patch({ partnerId: e.target.value })}>
              <option value="">거래처 선택</option>
              {partnersAll.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
            </select>
          )}
          {scn.kind === 'settlement_delay' && (
            <>
              <input aria-label="지연 일수" type="range" min={1} max={45} value={scn.days} disabled={!scn.partnerId} onChange={(e) => patch({ days: +e.target.value })} />
              <span className="num" style={{ minWidth: 34 }}>{scn.days}일</span>
            </>
          )}
          {scn.kind === 'loan_default' && (
            <select aria-label="대출" value={scn.loanId} onChange={(e) => patch({ loanId: e.target.value })}>
              {loans.map((l) => <option key={l.id} value={l.id}>{l.label}</option>)}
            </select>
          )}
          {scn.kind === 'payment_switch' && (
            <>
              <select aria-label="대상 지급" value={scn.payId} onChange={(e) => patch({ payId: e.target.value })}>
                {payTargets.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
              </select>
              <span>→</span>
              <select aria-label="카드" value={scn.cardId} onChange={(e) => patch({ cardId: e.target.value })}>
                {cards.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}
              </select>
              <label className="chk"><input type="checkbox" checked={scn.spendUnmet} onChange={(e) => patch({ spendUnmet: e.target.checked })} /> 실적 미충족</label>
            </>
          )}
          {scn.kind === 'revenue_drop' && (
            <>
              <input aria-label="매출 감소율" type="range" min={5} max={60} step={5} value={scn.pct} onChange={(e) => patch({ pct: +e.target.value })} />
              <span className="num" style={{ minWidth: 44 }}>−{scn.pct}%</span>
            </>
          )}
          {scn.kind === 'rate_up' && (
            <>
              <input aria-label="금리 상승폭" type="range" min={0.5} max={3} step={0.5} value={scn.pp} onChange={(e) => patch({ pp: +e.target.value })} />
              <span className="num" style={{ minWidth: 44 }}>+{scn.pp}%p</span>
            </>
          )}
        </div>
        <label className="chk"><input type="checkbox" checked={alwaysLabels} onChange={(e) => setAlwaysLabels(e.target.checked)} /> 라벨 항상</label>
        <button type="button" className={`btn ghost ${oppOpen ? 'on' : ''}`} aria-expanded={oppOpen} onClick={() => { setOppOpen((o) => !o); setSelected(null) }}>
          기회 {OPPS.length}
        </button>
      </div>
      <Legend />

      <div className="graph-wrap fill">
        <GraphView
          visible={shown}
          showLabels={alwaysLabels}
          nodeMarks={nodeMarks}
          edgeMarks={edgeMarks}
          replayKey={replay}
          selectedId={selected}
          onSelect={(id) => { setSelected(id); setFocus(null); if (id) setOppOpen(false) }}
        />

        {result && b && shock && (
          <section className="ov ov-spread" aria-label="시나리오 결과">
            <div className="res-head">
              <h2>{describe(shock)}</h2>
              <button type="button" className="replay" onClick={() => setReplay((k) => k + 1)} aria-label="전파 과정 다시 보기">▶ 다시 보기</button>
            </div>
            <p className="chips-row" aria-label="영향 요약">
              {counts.triggered > 0 && <span className="pill st-triggered">발동 {counts.triggered}</span>}
              {counts.at_risk > 0 && <span className="pill st-at_risk">위험 {counts.at_risk}</span>}
              {counts.improved > 0 && <span className="pill st-improved">개선 {counts.improved}</span>}
              {counts.changed > 0 && <span className="pill">변경 {counts.changed}</span>}
            </p>
            <div className="res-grid">
              <div><span>영향받은 노드</span><b className="num">{result.nodes.size}개</b></div>
              <div><span>예상 최저 잔액</span><b className={`num ${b.minP50 < 0 ? 'bad' : ''}`}>{won(b.minP50)}</b></div>
              <div><span>기준선 대비</span><b className={`num ${delta < 0 ? 'bad' : delta > 0 ? 'ok' : ''}`}>{delta > 0 ? '+' : ''}{won(delta)}</b></div>
              <div><span>첫 부족 예상일</span><b className="num">{b.firstShortDay ? dayLabel(b.firstShortDay) : '없음'}</b></div>
            </div>
            {b.repayments.length > 0 && (
              <>
                <h3 className="rel-h" style={{ margin: '8px 0 4px' }}>위험해진 상환</h3>
                <ul className="notes">{b.repayments.map((r) => <li key={r.id}>{r.label} {md(r.date)} · {won(r.amount)}{r.prob ? ` · 부족 확률 ${Math.round(r.prob * 100)}%` : ''}</li>)}</ul>
              </>
            )}
            <h3 className="rel-h" style={{ margin: '8px 0 4px' }}>전파 경로 ({result.hops}홉)</h3>
            <ul className="notes">{result.notes.map((n) => <li key={n}>{n}</li>)}</ul>
            {result.suggestions.map((sg) => <p className="notice" key={sg.signalId}>신호: {sg.text}</p>)}
          </section>
        )}

        {oppOpen && (
          <section className="ov ov-opp" aria-label="연결에서 찾은 기회">
            <h2>연결에서 찾은 기회</h2>
            <p className="sub" style={{ marginBottom: 8 }}>누르면 지도에서 관련 노드를 강조합니다. 비교 정보이며 권유가 아닙니다.</p>
            {OPPS.map((o) => (
              <button type="button" key={o.id} className="opp" onClick={() => { setSelected(null); setScn((c) => ({ ...c, kind: 'none' })); setFocus(o.nodes); setOppOpen(false) }}>
                <b>{o.title}</b>
                <span>{o.body}</span>
              </button>
            ))}
          </section>
        )}

        {sel && (
          <aside className="ov ov-detail card detail" aria-label="선택한 노드 상세">
            <button type="button" className="x" aria-label="닫기" onClick={() => setSelected(null)}>✕</button>
            <span className="pill">{TYPE_LABEL[sel.type]}</span>
            {result?.nodes.get(sel.id) && <span className={`pill st-${result.nodes.get(sel.id)!.status}`} style={{ marginLeft: 6 }}>{STATUS_LABEL[result.nodes.get(sel.id)!.status]}</span>}
            <h2 style={{ marginTop: 6 }}>{sel.label}</h2>
            {nodeSub(sel) && <p className="sub" style={{ marginBottom: 6 }}>{nodeSub(sel)}</p>}
            {result?.nodes.get(sel.id) && <p className="notice" style={{ marginTop: 0 }}>{result.nodes.get(sel.id)!.reason}</p>}
            <dl style={{ margin: 0 }}>
              {nodeLines(sel).filter(() => sel.type !== 'card').map(([k, v]) => (<div key={k}><dt>{k}</dt><dd>{v}</dd></div>))}
              {sel.type === 'card' && <div><dt>결제일 · 한도</dt><dd>매월 {sel.billingDay}일 · {sel.limit.toLocaleString('ko-KR')}원</dd></div>}
            </dl>

            {sel.type === 'card' && benefitStatus(sel).map((bf) => (
              <div className="benefit" key={bf.description}>
                <b>{bf.description}</b>
                <p className="muted">{bf.condition} · {bf.met === null ? '조건 없음' : bf.met ? <span className="ok">조건 충족</span> : <span className="bad">조건 미충족</span>}</p>
                <ul>
                  {bf.targets.map((t) => (
                    <li key={t.id}>{t.label}: 현재 {t.payingWith} → {t.applied ? <span className="ok">혜택 적용 중</span> : <span className="bad">미적용</span>}</li>
                  ))}
                </ul>
              </div>
            ))}

            {sel.type === 'contract' && (
              <>
                <h3 className="rel-h">조항 {clausesOf(sel).length}개</h3>
                <ul className="clauses">
                  {clausesOf(sel).map((c) => (
                    <li key={c.id}>
                      <button type="button" onClick={() => { setVisible((v) => new Set(v).add('clause')); setSelected(c.id) }}>
                        <span className="kind">{c.kindLabel}</span>
                        <b>{c.trigger}</b>
                        <span className="muted">→ {c.effect}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              </>
            )}

            <ReachList title="이 노드가 영향을 주는 것" items={down} dir="down" onPick={setSelected} />
            <ReachList title="이 노드가 영향을 받는 것" items={up} dir="up" onPick={setSelected} />

            {scenarioFor(sel) && (
              <button type="button" className="btn" style={{ width: '100%', marginTop: 12 }} onClick={() => startScenario(sel)}>
                이 노드에서 시나리오 시작 ({SCENARIO_LABEL[scenarioFor(sel)!.kind]})
              </button>
            )}
          </aside>
        )}
      </div>
    </div>
  )
}

function ReachList({ title, items, dir, onPick }: { title: string; items: ReturnType<typeof reach>; dir: 'down' | 'up'; onPick: (id: string) => void }) {
  return (
    <>
      <h3 className="rel-h">{title} {items.length}</h3>
      {items.length === 0 ? <p className="muted" style={{ fontSize: 13 }}>없음</p> : (
        <ul className="rels">
          {items.map((r) => (
            <li key={r.node.id}>
              <button type="button" onClick={() => onPick(r.node.id)}>
                <span className="kind">{(dir === 'down' ? r.via : [...r.via].reverse()).map((e) => EDGE_LABEL[e.type]).join(' → ')}{r.via.length > 1 ? ` · ${r.via.length}홉` : ''}</span>
                <b>{dir === 'down' ? '→' : '←'} {r.node.label}</b>
                <span className="muted">{TYPE_LABEL[r.node.type]}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </>
  )
}
