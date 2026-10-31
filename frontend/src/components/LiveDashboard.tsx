// 서버 계산 결과를 원래 홈 화면 구성에 끼워 넣는 조각들 (US-03·04·05·07). 화면은 숫자를 만들지 않는다.
import { useEffect, useState } from 'react'
import { signalReason } from '../live.ts'
import { Area, CartesianGrid, ComposedChart, Line, ReferenceArea, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, md, type DriverDto, type EvidenceDto, type ForecastDto } from '../api.ts'
import { won } from '../data.ts'

const LEVEL = { RED: { cls: 'red', ko: '위험' }, YELLOW: { cls: 'yellow', ko: '주의' }, GREEN: { cls: 'green', ko: '안정' } } as const

/** 원래 신호등과 같은 모양. 위험·주의일 때 누르면 영향 일정을 연다 (US-05 AC-04). */
export function LiveSignal({ f, open, onToggle }: { f: ForecastDto; open: boolean; onToggle: () => void }) {
  const lv = LEVEL[f.signal]
  return (
    <button type="button" className={`signal ${lv.cls} signal-btn`} onClick={onToggle} aria-expanded={open} disabled={f.signal === 'GREEN'}>
      <span className="lamp" aria-hidden />
      <div>
        <strong>자금 상태: {lv.ko}</strong>
        <p>{signalReason(f)}{f.signal !== 'GREEN' && (open ? ' 다시 누르면 닫혀요.' : ' 눌러서 영향을 준 일정을 확인하세요.')}</p>
      </div>
    </button>
  )
}

export function DriversCard({ runId, trigger }: { runId: number; trigger: string | null }) {
  const [drivers, setDrivers] = useState<DriverDto[] | null>(null)
  useEffect(() => { api<{ drivers: DriverDto[] }>(`/api/alerts/${runId}/drivers`).then((r) => setDrivers(r.drivers)) }, [runId])
  return (
    <section className="card" aria-labelledby="drv-h">
      <h2 id="drv-h">{trigger && md(trigger)} 경보에 영향을 준 일정</h2>
      {!drivers ? <p className="muted">불러오는 중…</p> : drivers.map((d) => (
        <div className="row" key={d.cash_event_id}>
          <span>{d.label}<br /><span className="muted">{md(d.date)} · {d.role === 'BEFORE' ? '경보일 전에 나가는 돈' : '경보일 뒤에 들어오는 돈'}</span></span>
          <b className={`num ${d.direction === 'OUT' ? 'bad' : ''}`}>{d.direction === 'OUT' ? '-' : '+'}{won(d.amount)}</b>
        </div>
      ))}
    </section>
  )
}

/** 12주 예상 잔액 (Recharts). 0원 위는 파랑, 아래는 빨강. days로 4주/12주를 고른다. */
export function LiveChart({ f, days, height = 250 }: { f: ForecastDto; days: number; height?: number }) {
  const daily = (f.daily ?? []).slice(0, days)
  const alertEnd = days > 28 ? daily[27]?.date : undefined
  const hi = Math.max(0, f.safety_balance, ...daily.map((d) => d.balance))
  const lo = Math.min(0, ...daily.map((d) => d.balance))
  const zeroAt = hi === lo ? 1 : hi / (hi - lo)
  const gid = `bal-${days}`
  return (
    <div style={{ width: '100%', height }}>
      <ResponsiveContainer>
        <ComposedChart data={daily} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id={`${gid}-s`} x1="0" y1="0" x2="0" y2="1"><stop offset={zeroAt} stopColor="var(--band)" /><stop offset={zeroAt} stopColor="var(--red)" /></linearGradient>
            <linearGradient id={`${gid}-f`} x1="0" y1="0" x2="0" y2="1"><stop offset={zeroAt} stopColor="var(--band)" stopOpacity={0.14} /><stop offset={zeroAt} stopColor="var(--red)" stopOpacity={0.22} /></linearGradient>
          </defs>
          <CartesianGrid stroke="var(--rule)" vertical={false} />
          <XAxis dataKey="date" tickFormatter={md} interval={days > 28 ? 13 : 6} tick={{ fontSize: 11, fill: 'var(--muted)' }} />
          <YAxis domain={[lo, hi]} tickFormatter={(v: number) => `${Math.round(v / 10000)}만`} width={48} tick={{ fontSize: 11, fill: 'var(--muted)' }} />
          <Tooltip formatter={(v: number) => [won(v), '예상 잔액']} labelFormatter={(l: string) => md(l)} />
          {alertEnd && <ReferenceArea x1={daily[0].date} x2={alertEnd} fill="var(--muted)" fillOpacity={0.07} />}
          <ReferenceLine y={f.safety_balance} stroke="var(--yellow)" strokeDasharray="4 4" />
          <Area type="stepAfter" dataKey="balance" baseValue={0} stroke="none" fill={`url(#${gid}-f)`} isAnimationActive={false} />
          <ReferenceLine y={0} stroke="var(--ink)" strokeWidth={1.2} />
          <Line type="stepAfter" dataKey="balance" stroke={`url(#${gid}-s)`} strokeWidth={2} dot={false} isAnimationActive={false} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}

/** 원래 "왜 자금 상태가 위험일까요?" 자리에 들어가는 근거 카드 (US-07 AC-02·03). */
export function LiveWhy({ f }: { f: ForecastDto }) {
  const [ev, setEv] = useState<{ items: EvidenceDto[]; message: string | null } | null>(null)
  const level = f.signal === 'RED' ? '위험' : '주의'
  const show = () => api<{ evidence: EvidenceDto[]; message: string | null }>(`/api/alerts/${f.run_id}/evidence`)
    .then((r) => setEv({ items: r.evidence, message: r.message })).catch((e) => setEv({ items: [], message: e.message }))
  return (
    <section className="why card" aria-labelledby="why-h">
      <div className="row-head"><h2 id="why-h">왜 자금 상태가 “{level}”일까요?</h2>{!ev && <button className="btn" onClick={show}>이유 보기</button>}</div>
      <p className="sub">{signalReason(f)} {f.shortage_amount ? `부족액 ${won(f.shortage_amount)}.` : ''}</p>
      {ev && (ev.items.length ? (
        <ol className="evidence">
          {ev.items.map((e) => <li key={e.id}><span className={`pill ${e.type === 'GRAPH_PATH' ? '' : 'soon'}`}>{e.id}</span> {e.text}</li>)}
        </ol>
      ) : <p className="muted">{ev.message ?? '근거 없음'}</p>)}
      {ev && <p className="muted small">P = 거래관계 경로(금융지도), D = 계약 문서 조각. 금액은 계산 모듈 결과입니다.</p>}
    </section>
  )
}
