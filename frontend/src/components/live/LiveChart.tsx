// 12주 예상 잔액 차트 (US-03, T12). 화면은 숫자를 만들지 않고 서버 계산 결과만 그린다.
import { Area, CartesianGrid, ComposedChart, Line, ReferenceArea, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { md, type ForecastDto } from '../../api.ts'
import { won } from '../../data.ts'

/** 12주 예상 잔액 (Recharts). 0원 위는 파랑, 아래는 빨강. days로 4주/12주를 고른다. */
export default function LiveChart({ f, days, height = 250 }: { f: ForecastDto; days: number; height?: number }) {
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

