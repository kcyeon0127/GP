// 대응안 비교·승인 (US-10) 서버 모드. 후보와 효과(최저 잔액·부족일)는 모두 백엔드(ResponseService)가 계산한다.
// 화면은 숫자를 만들지 않고, 승인 전에는 아무 일정도 바꾸지 않는다 (AC-03).
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { CartesianGrid, ComposedChart, Legend, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, md, type ApiError, type ForecastDto, type SignalLevel } from '../../api.ts'
import { won } from '../../data.ts'

interface Result {
  signal: SignalLevel; first_shortage_date: string | null; shortage_amount: number | null
  min_balance: number; min_balance_date: string; alert_min_balance: number; daily: { date: string; balance: number }[]
}
interface PlanDto {
  plan_id: number; kind: string; kind_ko: string; title: string; description: string; caution: string
  target: { date: string; amount: number }; parts: { due_date: string; amount: number }[]
  result: Result; status: string; evidence: { id: string; text: string | null }[]; evidence_missing: boolean
}
interface ProposalDto { run_id: number; base: Result; plans: PlanDto[]; evidence: { id: string; type: string; text: string }[]; message: string | null }

const SIGNAL_KO: Record<SignalLevel, string> = { RED: '위험', YELLOW: '주의', GREEN: '안전' }
const day = (d: string | null) => (d ? md(d) : '없음')

function CompareChart({ base, plan }: { base: Result; plan: PlanDto }) {
  const data = base.daily.map((d, i) => ({ date: d.date, base: d.balance, plan: plan.result.daily[i]?.balance }))
  const vals = data.flatMap((d) => [d.base, d.plan ?? 0])
  return (
    <div style={{ width: '100%', height: 240 }}>
      <ResponsiveContainer>
        <ComposedChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="var(--rule)" vertical={false} />
          <XAxis dataKey="date" tickFormatter={md} interval={13} tick={{ fontSize: 11, fill: 'var(--muted)' }} />
          <YAxis domain={[Math.min(0, ...vals), Math.max(0, ...vals)]} tickFormatter={(v: number) => `${Math.round(v / 10000)}만`} width={52} tick={{ fontSize: 11, fill: 'var(--muted)' }} />
          <Tooltip formatter={(v: number, n: string) => [won(v), n === 'base' ? '지금 일정' : '이 대응안']} labelFormatter={(l: string) => md(l)} />
          <Legend formatter={(v: string) => (v === 'base' ? '지금 일정' : '이 대응안')} />
          <ReferenceLine y={0} stroke="var(--ink)" strokeWidth={1.2} />
          <Line type="stepAfter" dataKey="base" stroke="var(--red)" strokeWidth={2} dot={false} isAnimationActive={false} />
          <Line type="stepAfter" dataKey="plan" stroke="var(--green)" strokeWidth={2} dot={false} isAnimationActive={false} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}

export default function LiveAgent() {
  const [p, setP] = useState<ProposalDto | null>(null)
  const [approved, setApproved] = useState<PlanDto[]>([])
  const [pick, setPick] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')
  const [done, setDone] = useState<{ plan: PlanDto; f: ForecastDto } | null>(null)

  const loadApproved = () => api<PlanDto[]>('/api/response-plans/approved').then(setApproved).catch(() => setApproved([]))
  useEffect(() => { loadApproved() }, [])

  const request = async () => {
    setBusy(true); setMsg(''); setDone(null)
    try {
      const r = await api<ProposalDto>('/api/response-plans', { method: 'POST' })
      setP(r); setPick(r.plans[0]?.plan_id ?? null)
    } catch (e) {
      setMsg((e as ApiError).message ?? '대응안을 만들지 못했어요. 서버 연결을 확인한 뒤 다시 눌러 주세요.')
    } finally { setBusy(false) }
  }
  const decide = async (id: number, action: 'approve' | 'cancel') => {
    setBusy(true); setMsg('')
    try {
      const r = await api<{ plan: PlanDto; forecast: ForecastDto }>(`/api/response-plans/${id}/${action}`, { method: 'POST' })
      if (action === 'approve') { setDone({ plan: r.plan, f: r.forecast }); setP(null) } else setDone(null)
      loadApproved()
    } catch (e) {
      setMsg((e as ApiError).message)
    } finally { setBusy(false) }
  }
  const sel = p?.plans.find((x) => x.plan_id === pick) ?? null
  const evText = (id: string) => p?.evidence.find((e) => e.id === id)?.text ?? undefined

  return (
    <>
      <div className="page-head"><Link to="/" className="back">← 홈</Link><h1>대응안: 무엇부터 할까요?</h1></div>
      <div className="agent-grid">
        <div className="stack">
          {done ? (
            <div className="card" role="status">
              <h2>“{done.plan.title}”을 승인했어요</h2>
              <p className="sub">일정에 반영하고 예상 잔액을 다시 계산했어요. 거래처·은행과의 협의는 사장님이 직접 해 주세요.</p>
              <div className="kpis">
                <div className="kpi"><span>4주 신호</span><b>{SIGNAL_KO[done.f.signal]}</b></div>
                <div className="kpi"><span>12주 최저 잔액</span><b className={`num ${done.f.min_balance < 0 ? 'bad' : ''}`}>{won(done.f.min_balance)}</b></div>
                <div className="kpi"><span>최초 부족일</span><b className="num">{day(done.f.first_shortage_date)}</b></div>
              </div>
              <p style={{ marginTop: 14 }}><Link className="btn" to="/" style={{ textDecoration: 'none', display: 'inline-block' }}>홈에서 확인</Link></p>
            </div>
          ) : !p ? (
            <div className="card">
              <h2>지금 일정으로 대응안을 찾아볼까요?</h2>
              <p className="sub">경보일까지 나가는 돈 중 하나를 골라 언제 낼지 바꿔 보고, 효과를 계산 모듈로 다시 계산해 비교해요. 승인하기 전에는 일정이 바뀌지 않아요.</p>
              <button className="btn" onClick={request} disabled={busy}>{busy ? '계산하는 중…' : '대응안 찾기'}</button>
            </div>
          ) : (
            <>
              <div className="card">
                <p className="sub" style={{ marginBottom: 6 }}>
                  지금 일정: 4주 신호 <b>{SIGNAL_KO[p.base.signal]}</b>, 최초 부족일 <b className="num">{day(p.base.first_shortage_date)}</b>, 4주 최저 잔액 <b className={`num ${p.base.alert_min_balance < 0 ? 'bad' : ''}`}>{won(p.base.alert_min_balance)}</b>
                </p>
                {p.message && <p className="muted" role="status">{p.message}</p>}
                {sel && <CompareChart base={p.base} plan={sel} />}
              </div>
              {p.plans.length > 0 && (
                <div className="card" style={{ overflowX: 'auto' }}>
                  <h2>후보 비교</h2>
                  <table className="table">
                    <thead><tr><th>대응안</th><th>4주 신호</th><th>4주 최저 잔액</th><th>최초 부족일</th></tr></thead>
                    <tbody>
                      <tr className="muted"><td>지금 일정</td><td>{SIGNAL_KO[p.base.signal]}</td><td className="num">{won(p.base.alert_min_balance)}</td><td className="num">{day(p.base.first_shortage_date)}</td></tr>
                      {p.plans.map((x) => (
                        <tr key={x.plan_id}><td>{x.kind_ko}</td><td>{SIGNAL_KO[x.result.signal]}</td>
                          <td className={`num ${x.result.alert_min_balance < 0 ? 'bad' : ''}`}>{won(x.result.alert_min_balance)}</td><td className="num">{day(x.result.first_shortage_date)}</td></tr>
                      ))}
                    </tbody>
                  </table>
                  <p className="muted small">최초 부족일은 12주 구간 기준이에요. 한 번만 옮기는 안이라 다음 달 같은 지급에서 다시 모자랄 수 있어요.</p>
                </div>
              )}
            </>
          )}
          {msg && <p className="form-msg" role="alert">{msg}</p>}
        </div>

        <div>
          {p && p.plans.map((x, i) => (
            <article className={`plan ${x.plan_id === pick ? 'top' : ''}`} key={x.plan_id} onClick={() => setPick(x.plan_id)}>
              <header>
                <h3>{x.title}</h3>
                <span className={`pill ${x.result.signal === 'RED' ? 'red' : x.result.signal === 'YELLOW' ? 'yellow' : 'green'}`}>{i === 0 ? '효과 1위 · ' : ''}{SIGNAL_KO[x.result.signal]}</span>
              </header>
              <p>{x.description}</p>
              <p className="evlist">
                {x.evidence_missing ? <span className="muted small">이 안에 붙일 근거를 찾지 못했어요.</span>
                  : x.evidence.map((e) => <span className="ev" key={e.id} title={e.text ?? evText(e.id)}>{e.id}</span>)}
              </p>
              <p className="cost">{x.caution}</p>
              <button className="btn" disabled={busy} onClick={(ev) => { ev.stopPropagation(); decide(x.plan_id, 'approve') }}>이 안 승인</button>
            </article>
          ))}
          {p && p.plans.length > 0 && <button className="btn ghost" onClick={request} disabled={busy}>다시 계산</button>}
          {approved.length > 0 && (
            <div className="card" style={{ marginTop: 16 }}>
              <h2>승인한 대응안 <span className="count">{approved.length}</span></h2>
              {approved.map((x) => (
                <div className="row" key={x.plan_id}>
                  <span>{x.title}<br /><span className="muted">{md(x.target.date)} → {x.parts.map((pt) => `${md(pt.due_date)} ${won(pt.amount)}`).join(', ')}</span></span>
                  <button className="btn ghost" disabled={busy} onClick={() => decide(x.plan_id, 'cancel')}>되돌리기</button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </>
  )
}
