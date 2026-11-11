// What-if 시나리오 (US-09) 서버 모드: 조건을 골라 서버 계산 결과를 기준안과 겹쳐 본다.
// 화면은 숫자를 만들지 않는다. 시나리오 규칙과 잔액 계산은 모두 백엔드(ScenarioService)가 한다.
import { useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { CartesianGrid, ComposedChart, Legend, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, md, type ApiError, type CounterpartyDto } from '../../api.ts'
import { won } from '../../data.ts'

interface Summary {
  signal: 'RED' | 'YELLOW' | 'GREEN'; first_shortage_date: string | null; shortage_amount: number | null
  min_balance: number; min_balance_date: string; daily: { date: string; balance: number }[]
}
interface ScenarioDto {
  scenario_id: number; kinds: string[]; base: Summary; scenario: Summary
  new_shortages: { event_id: number; date: string; label: string; amount: number; balance: number }[]
  changes: { event_id: number; label: string; before_date: string; after_date: string | null; before_amount: number; after_amount: number }[]
}
const SIGNAL_KO = { RED: '위험', YELLOW: '주의', GREEN: '안전' } as const
const FIELD_MSG: Record<string, string> = {
  days: '지연 일수는 1~60일로 입력하세요.', revenue_drop_pct: '매출 감소율은 0보다 크고 90% 이하로 입력하세요.',
  cost_rise_pct: '원가 상승률은 0보다 크고 100% 이하로 입력하세요.', rate_rise_pp: '금리 상승폭은 0보다 크고 10%p 이하로 입력하세요.',
}

function CompareChart({ r }: { r: ScenarioDto }) {
  const data = r.base.daily.map((d, i) => ({ date: d.date, base: d.balance, scenario: r.scenario.daily[i]?.balance }))
  const vals = data.flatMap((d) => [d.base, d.scenario ?? 0])
  return (
    <div style={{ width: '100%', height: 280 }}>
      <ResponsiveContainer>
        <ComposedChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="var(--rule)" vertical={false} />
          <XAxis dataKey="date" tickFormatter={md} interval={13} tick={{ fontSize: 11, fill: 'var(--muted)' }} />
          <YAxis domain={[Math.min(0, ...vals), Math.max(0, ...vals)]} tickFormatter={(v: number) => `${Math.round(v / 10000)}만`} width={52} tick={{ fontSize: 11, fill: 'var(--muted)' }} />
          <Tooltip formatter={(v: number, n: string) => [won(v), n === 'base' ? '기준안' : '시나리오']} labelFormatter={(l: string) => md(l)} />
          <Legend formatter={(v: string) => (v === 'base' ? '기준안' : '시나리오')} />
          <ReferenceLine y={0} stroke="var(--ink)" strokeWidth={1.2} />
          <Line type="stepAfter" dataKey="base" stroke="var(--band)" strokeWidth={2} dot={false} isAnimationActive={false} />
          <Line type="stepAfter" dataKey="scenario" stroke="var(--red)" strokeWidth={2} dot={false} isAnimationActive={false} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}

const day = (d: string | null) => (d ? md(d) : '없음')

// 기존 데모처럼 조건을 바꿀 때마다 계산하지 않고 버튼을 둔다: 실행마다 시나리오가 DB에 저장되기 때문이다.
// 슬라이더 대신 숫자 칸을 쓰는 이유: 0처럼 범위 밖 값도 넣을 수 있어야 범위 안내(AC-07)가 동작한다.
// 처음 켜 둔 조건은 AC-01과 같다 (정산 15일 지연 + 원가 10% 상승).
export default function LiveSimulation() {
  const [sales, setSales] = useState<CounterpartyDto[]>([])
  const [on, setOn] = useState({ delay: true, revenue: false, cost: true, rate: false })
  const [cp, setCp] = useState('')
  const [days, setDays] = useState('15')
  const [revenue, setRevenue] = useState('15')
  const [cost, setCost] = useState('10')
  const [rate, setRate] = useState('1')
  const [r, setR] = useState<ScenarioDto | null>(null)
  const [msg, setMsg] = useState('')
  useEffect(() => {
    api<CounterpartyDto[]>('/api/counterparties').then((cs) => {
      const s = cs.filter((c) => c.trade_type === 'SALES')
      setSales(s)
      if (s[0]) setCp(String(s[0].counterparty_id))
    })
  }, [])
  const run = async (e?: FormEvent) => {
    e?.preventDefault()
    const body: Record<string, unknown> = {}
    if (on.delay && cp) body.settlement_delay = { counterparty_id: +cp, days: +days }
    if (on.revenue) body.revenue_drop_pct = +revenue
    if (on.cost) body.cost_rise_pct = +cost
    if (on.rate) body.rate_rise_pp = +rate
    try {
      setR(await api<ScenarioDto>('/api/scenarios', { method: 'POST', body }))
      setMsg('')
    } catch (ex) {
      const ae = ex as ApiError
      setR(null) // 범위를 벗어나면 계산하지 않는다 (AC-07)
      setMsg(ae.fields?.length ? ae.fields.map((f) => FIELD_MSG[f] ?? f).join(' ') : ae.message)
    }
  }
  const toggle = (k: keyof typeof on) => setOn((v) => ({ ...v, [k]: !v[k] }))
  const row = (k: keyof typeof on, label: string, input: React.ReactNode) => (
    <div className={`cond ${on[k] ? 'on' : ''}`}>
      <label className="cond-head"><input type="checkbox" checked={on[k]} onChange={() => toggle(k)} /> {label}</label>
      {on[k] && <div className="cond-body">{input}</div>}
    </div>
  )

  return (
    <>
      <div className="page-head"><Link to="/" className="back">← 홈</Link><h1>시나리오: 이러면 어떻게 될까요?</h1></div>
      <div className="hub-grid">
        <div className="stack">
          {!r ? (
            <div className="card"><h2>조건을 고르고 "시나리오 계산"을 누르세요</h2><p className="sub">등록한 일정을 복사해서 계산하므로 원래 일정과 홈 화면의 예상 잔액은 바뀌지 않아요.</p></div>
          ) : (
            <>
              <div className="card">
                <div className="kpis compare">
                  <div className="kpi"><span>최초 부족일</span><b className="num">{day(r.base.first_shortage_date)} → <strong className={r.scenario.first_shortage_date ? 'bad' : ''}>{day(r.scenario.first_shortage_date)}</strong></b></div>
                  <div className="kpi"><span>12주 최저 잔액</span><b className="num">{won(r.base.min_balance)} → <strong className={r.scenario.min_balance < 0 ? 'bad' : ''}>{won(r.scenario.min_balance)}</strong></b></div>
                  <div className="kpi"><span>4주 신호</span><b>{SIGNAL_KO[r.base.signal]} → {SIGNAL_KO[r.scenario.signal]}</b></div>
                </div>
                <CompareChart r={r} />
              </div>
              <div className="card">
                <h2>새로 부족해지는 지급 <span className="count">{r.new_shortages.length}</span></h2>
                {r.new_shortages.length === 0 ? <p className="sub" style={{ marginBottom: 0 }}>기준안에서 낼 수 있던 지급 중 새로 모자라는 것은 없어요.</p> : (
                  <>
                    <p className="sub">기준안에서는 낼 수 있었지만 이 조건에서는 그날 잔액이 0원 아래가 되는 지급이에요.</p>
                    {r.new_shortages.map((x) => (
                      <div className="row" key={x.event_id}><span>{x.label}<br /><span className="muted">{md(x.date)} · 그날 잔액 {won(x.balance)}</span></span><b className="num bad">-{won(x.amount)}</b></div>
                    ))}
                    <p style={{ marginTop: 14, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                      <Link className="btn" to="/agent" style={{ textDecoration: 'none', display: 'inline-block' }}>대응안 보기</Link>
                      <Link className="btn ghost" to={`/map/mine?scenario=${r.scenario_id}`} style={{ textDecoration: 'none', display: 'inline-block' }}>금융지도에서 영향 경로 보기</Link>
                    </p>
                  </>
                )}
              </div>
              {r.changes.length > 0 && (
                <details className="card">
                  <summary>조건 때문에 바뀐 일정 {r.changes.length}건</summary>
                  {r.changes.map((c) => (
                    <div className="row" key={c.event_id}><span>{c.label}<br /><span className="muted">{md(c.before_date)} → {c.after_date ? md(c.after_date) : '12주 밖'}</span></span>
                      <span className="num">{won(Math.abs(c.before_amount))} → <b>{won(Math.abs(c.after_amount))}</b></span></div>
                  ))}
                </details>
              )}
            </>
          )}
        </div>
        <div className="stack">
          <form className="card" onSubmit={run}>
            <h2>조건</h2>
            <p className="sub">여러 조건을 함께 골라도 돼요.</p>
            {row('delay', '정산 지연', (
              <>
                <select aria-label="정산을 미룰 매출처" value={cp} onChange={(e) => setCp(e.target.value)}>
                  {sales.length === 0 && <option value="">매출처를 먼저 등록하세요</option>}
                  {sales.map((s) => <option key={s.counterparty_id} value={s.counterparty_id}>{s.name}</option>)}
                </select>
                <label className="inline"><input type="number" inputMode="numeric" value={days} onChange={(e) => setDays(e.target.value)} aria-label="지연 일수" /> 일 늦게</label>
              </>
            ))}
            {row('revenue', '매출 감소', <label className="inline"><input type="number" value={revenue} onChange={(e) => setRevenue(e.target.value)} aria-label="매출 감소율" /> % 줄어듦</label>)}
            {row('cost', '원가 상승', <label className="inline"><input type="number" value={cost} onChange={(e) => setCost(e.target.value)} aria-label="원가 상승률" /> % 오름 (매입 대금)</label>)}
            {row('rate', '금리 상승', <label className="inline"><input type="number" step="0.1" value={rate} onChange={(e) => setRate(e.target.value)} aria-label="금리 상승폭" /> %p 오름 (변동금리 대출)</label>)}
            <p className="form-msg" role="alert">{msg}</p>
            <button className="btn" type="submit">시나리오 계산</button>
          </form>
        </div>
      </div>
    </>
  )
}
