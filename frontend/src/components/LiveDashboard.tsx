// 조기경보 대시보드 (US-03·04·05·07): 서버 계산 결과만 보여 준다. 화면은 숫자를 만들지 않는다.
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Area, CartesianGrid, ComposedChart, Line, ReferenceArea, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, md, type DriverDto, type EvidenceDto, type ForecastDto } from '../api.ts'
import { won } from '../data.ts'

const LEVEL = { RED: { cls: 'red', ko: '위험' }, YELLOW: { cls: 'yellow', ko: '주의' }, GREEN: { cls: 'green', ko: '안정' } } as const

export default function LiveDashboard() {
  const [f, setF] = useState<ForecastDto | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [balance, setBalance] = useState('')
  const [drivers, setDrivers] = useState<DriverDto[] | null>(null)
  const [evidence, setEvidence] = useState<{ items: EvidenceDto[]; message: string | null } | null>(null)

  const run = (body: object = {}) => {
    setDrivers(null)
    setEvidence(null)
    api<ForecastDto>('/api/forecasts', { method: 'POST', body }).then(setF).catch((e) => setErr(e.message))
  }
  useEffect(() => {
    api<ForecastDto>('/api/forecasts', { method: 'POST', body: {} }).then(setF).catch((e) => setErr(e.message))
  }, [])

  if (err) return <div className="card" role="alert">서버 계산을 불러오지 못했습니다: {err}</div>
  if (!f) return <div className="card">계산 중…</div>

  const lv = LEVEL[f.signal]
  const trigger = f.signal === 'RED' ? f.first_shortage_date : f.first_below_safe_date
  const reason = f.signal === 'RED' ? `${md(f.first_shortage_date!)}에 잔액이 0원 아래로 내려갑니다.`
    : f.signal === 'YELLOW' ? `${md(f.first_below_safe_date!)}에 잔액이 안전 잔액(${won(f.safety_balance)})보다 적어집니다.`
    : `4주 안에 잔액이 안전 잔액(${won(f.safety_balance)}) 아래로 내려가지 않습니다.`
  const daily = f.daily ?? []
  const alertEnd = daily[27]?.date
  // 0원 위·아래 색을 나누는 그라디언트 위치 (위쪽 끝 = 0, 아래쪽 끝 = 1)
  const hi = Math.max(0, ...daily.map((d) => d.balance))
  const lo = Math.min(0, ...daily.map((d) => d.balance))
  const zeroAt = hi === lo ? 1 : hi / (hi - lo)
  const toggleDrivers = () => {
    if (f.signal === 'GREEN') return
    if (drivers) return setDrivers(null)
    api<{ drivers: DriverDto[] }>(`/api/alerts/${f.run_id}/drivers`).then((r) => setDrivers(r.drivers))
  }
  const showEvidence = () => api<{ evidence: EvidenceDto[]; message: string | null }>(`/api/alerts/${f.run_id}/evidence`)
    .then((r) => setEvidence({ items: r.evidence, message: r.message }))
    .catch((e) => setEvidence({ items: [], message: e.message }))

  return (
    <div className="stack">
      <button type="button" className={`signal ${lv.cls} signal-btn`} onClick={toggleDrivers} aria-expanded={!!drivers} disabled={f.signal === 'GREEN'}>
        <span className="lamp" aria-hidden />
        <div>
          <strong>자금 상태: {lv.ko}</strong>
          <p>{reason}{f.signal !== 'GREEN' && ' 눌러서 영향을 준 일정을 확인하세요.'}</p>
        </div>
      </button>

      {drivers && (
        <section className="card" aria-labelledby="drv-h">
          <h2 id="drv-h">{trigger && md(trigger)} 경보에 영향을 준 일정</h2>
          {drivers.map((d) => (
            <div className="row" key={d.cash_event_id}>
              <span>{d.label}<br /><span className="muted">{md(d.date)} · {d.role === 'BEFORE' ? '경보일 전에 나가는 돈' : '경보일 뒤에 들어오는 돈'}</span></span>
              <b className={`num ${d.direction === 'OUT' ? 'bad' : ''}`}>{d.direction === 'OUT' ? '-' : '+'}{won(d.amount)}</b>
            </div>
          ))}
        </section>
      )}

      <div className="kpis">
        <div className="kpi"><span>최초 부족일</span><b className={`num ${f.first_shortage_date ? 'bad' : ''}`}>{f.first_shortage_date ? md(f.first_shortage_date) : '부족 예상 없음'}</b></div>
        <div className="kpi"><span>부족액</span><b className={`num ${f.shortage_amount ? 'bad' : ''}`}>{f.shortage_amount ? won(f.shortage_amount) : '-'}</b></div>
        <div className="kpi"><span>12주 최저 잔액</span><b className={`num ${f.min_balance < 0 ? 'bad' : ''}`}>{won(f.min_balance)} <small className="muted">{md(f.min_balance_date)}</small></b></div>
      </div>

      <section className="card">
        <h2>향후 12주 예상 잔액</h2>
        <p className="sub">기준일 {md(f.base_date)} · 현재 잔액 {won(f.start_balance)} · 회색 음영은 4주 경보 구간, 노란 점선은 안전 잔액, 빨간 부분은 0원 아래(부족)예요.</p>
        {!f.has_events && <p className="empty-note">{f.message} <Link to="/ledger">일정 등록하기 →</Link></p>}
        <div style={{ width: '100%', height: 260 }}>
          <ResponsiveContainer>
            <ComposedChart data={daily} margin={{ top: 8, right: 12, bottom: 0, left: 8 }}>
              <defs>
                <linearGradient id="bal-stroke" x1="0" y1="0" x2="0" y2="1">
                  <stop offset={zeroAt} stopColor="var(--band)" />
                  <stop offset={zeroAt} stopColor="var(--red)" />
                </linearGradient>
                <linearGradient id="bal-fill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset={zeroAt} stopColor="var(--band)" stopOpacity={0.14} />
                  <stop offset={zeroAt} stopColor="var(--red)" stopOpacity={0.22} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="var(--rule)" vertical={false} />
              <XAxis dataKey="date" tickFormatter={md} interval={13} tick={{ fontSize: 11, fill: 'var(--muted)' }} />
              <YAxis tickFormatter={(v: number) => `${Math.round(v / 10000)}만`} width={52} tick={{ fontSize: 11, fill: 'var(--muted)' }} />
              <Tooltip formatter={(v: number) => [won(v), '예상 잔액']} labelFormatter={(l: string) => md(l)} />
              {alertEnd && <ReferenceArea x1={daily[0].date} x2={alertEnd} fill="var(--muted)" fillOpacity={0.07} />}
              <ReferenceLine y={f.safety_balance} stroke="var(--yellow)" strokeDasharray="4 4" />
              <Area type="stepAfter" dataKey="balance" baseValue={0} stroke="none" fill="url(#bal-fill)" isAnimationActive={false} />
              <ReferenceLine y={0} stroke="var(--ink)" strokeWidth={1.2} label={{ value: '0원', position: 'insideTopLeft', fontSize: 11, fill: 'var(--muted)' }} />
              <Line type="stepAfter" dataKey="balance" stroke="url(#bal-stroke)" strokeWidth={2} dot={false} isAnimationActive={false} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
        <form className="rerun" onSubmit={(e) => { e.preventDefault(); if (balance) run({ current_balance: +balance }) }}>
          <label htmlFor="bal">현재 잔액 바꿔서 다시 계산</label>
          <input id="bal" type="number" inputMode="numeric" placeholder={String(f.start_balance)} value={balance} onChange={(e) => setBalance(e.target.value)} />
          <button className="btn ghost" type="submit">다시 계산</button>
        </form>
      </section>

      {f.signal !== 'GREEN' && (
        <section className="card" aria-labelledby="ev-h">
          <div className="row-head"><h2 id="ev-h">왜 모자랄까요?</h2>{!evidence && <button className="btn" onClick={showEvidence}>이유 보기</button>}</div>
          {evidence && (evidence.items.length ? (
            <ol className="evidence">
              {evidence.items.map((e) => (
                <li key={e.id}><span className={`pill ${e.type === 'GRAPH_PATH' ? '' : 'soon'}`}>{e.id}</span> {e.text}</li>
              ))}
            </ol>
          ) : <p className="muted">{evidence.message ?? '근거 없음'}</p>)}
          {evidence && <p className="muted small">P = 거래관계 경로(금융지도), D = 계약 문서 조각. 금액은 계산 모듈 결과입니다.</p>}
        </section>
      )}
    </div>
  )
}
