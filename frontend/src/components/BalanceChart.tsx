import { useId } from 'react'
import type { Forecast } from '../engine.ts'
import { HORIZON, WINDOW } from '../engine.ts'
import { business, dayLabel, won } from '../data.ts'

interface Props {
  base: Forecast
  scenario?: Forecast
  /** 과거 실제 잔액. 마지막 값이 오늘(D0)이고 앞쪽이 과거. 주어지면 미래 구간은 점선으로 그린다. */
  history?: number[]
  height?: number
  /** 그래프를 그리는 기준 폭. 좁은 칸에 넣을 때는 줄여서 글자 크기를 지킨다. */
  width?: number
  /** 보여 줄 미래 일수. 기본은 4주 경보 구간, HORIZON이면 12주 전체와 경보 구간 음영을 그린다. */
  days?: number
}

const PAD = { l: 56, r: 14, t: 12, b: 26 }

export default function BalanceChart({ base: fullBase, scenario: fullScenario, history, height = 280, width: W = 760, days = WINDOW }: Props) {
  const uid = useId()
  const past = history ? history.length - 1 : 0 // 오늘 이전 일수
  const cut = (f: Forecast): Forecast => ({ ...f, p10: f.p10.slice(0, days + 1), p50: f.p50.slice(0, days + 1), p90: f.p90.slice(0, days + 1) })
  const base = cut(fullBase)
  const scenario = fullScenario && cut(fullScenario)
  const series = scenario ? [base, scenario] : [base]
  const all = [...series.flatMap((f) => [...f.p10, ...f.p90]), ...(history ?? [])]
  const lo = Math.min(0, ...all)
  const hi = Math.max(...all)
  const span = hi - lo || 1
  const x = (d: number) => PAD.l + ((d + past) / (days + past)) * (W - PAD.l - PAD.r)
  const y = (v: number) => PAD.t + (1 - (v - lo) / span) * (height - PAD.t - PAD.b)
  const line = (arr: number[], from = 0) => arr.map((v, i) => `${i ? 'L' : 'M'}${x(from + i)},${y(v)}`).join(' ')
  const band = (f: Forecast) =>
    `${f.p90.map((v, d) => `${d ? 'L' : 'M'}${x(d)},${y(v)}`).join(' ')} ${f.p10
      .map((_, d) => d)
      .reverse()
      .map((d) => `L${x(d)},${y(f.p10[d])}`)
      .join(' ')} Z`
  const ticks = Array.from({ length: 4 }, (_, i) => lo + (span * i) / 3)
  const zeroY = y(business.minBalance)
  const main = scenario ?? base
  const minDay = main.p50.reduce((m, v, d) => (d && v < main.p50[m] ? d : m), 1)
  const futureDashed = !!scenario || !!history
  const step = days > WINDOW ? 14 : 7
  const xTicks = [...(history && days <= WINDOW ? [-past] : []), ...Array.from({ length: Math.floor(days / step) + 1 }, (_, i) => i * step)]
  const full = days >= HORIZON

  return (
    <svg className="chart" viewBox={`0 0 ${W} ${height}`} width="100%" role="img" aria-label={`${history ? `과거 ${past}일 잔액과 ` : ''}향후 ${days}일 잔액 예측. 최저 잔액 ${won(main.p50[minDay])}, ${dayLabel(minDay)} 전후.`}>
      <defs>
        <clipPath id={`${uid}-neg`}><rect x="0" y={zeroY} width={W} height={height} /></clipPath>
      </defs>
      {ticks.map((t) => (
        <g key={t}>
          <line className="grid" x1={PAD.l} x2={W - PAD.r} y1={y(t)} y2={y(t)} />
          <text x={PAD.l - 8} y={y(t) + 4} textAnchor="end">{(t / 10000).toFixed(0)}만</text>
        </g>
      ))}
      {xTicks.map((d) => (
        <text key={d} x={x(d)} y={height - 6} textAnchor={d === xTicks[xTicks.length - 1] ? 'end' : 'middle'}>{dayLabel(d)}</text>
      ))}
      {full && (
        <g>
          <rect x={x(0)} y={PAD.t} width={x(WINDOW) - x(0)} height={height - PAD.t - PAD.b} fill="var(--band)" opacity="0.06" />
          <text x={x(WINDOW) - 6} y={PAD.t + 10} textAnchor="end">4주 경보 구간</text>
        </g>
      )}
      {history && (
        <g>
          <line x1={x(0)} x2={x(0)} y1={PAD.t} y2={height - PAD.b} stroke="var(--muted)" strokeWidth="1" strokeDasharray="2 3" />
          <text x={x(0) + 6} y={PAD.t + 10}>오늘</text>
        </g>
      )}
      <path d={band(base)} fill="var(--band)" opacity={scenario ? 0.1 : 0.2} />
      {history && <path d={line(history, -past)} fill="none" stroke="var(--band)" strokeWidth="2.4" />}
      <path d={line(base.p50)} fill="none" stroke="var(--band)" strokeWidth="2" strokeDasharray={futureDashed ? '5 4' : undefined} />
      {scenario && (
        <>
          <path d={band(scenario)} fill="var(--red)" opacity="0.16" />
          <path d={line(scenario.p50)} fill="none" stroke="var(--red)" strokeWidth="2.4" />
        </>
      )}
      <line x1={PAD.l} x2={W - PAD.r} y1={zeroY} y2={zeroY} stroke="var(--red)" strokeWidth="1.2" strokeDasharray="2 3" />
      <circle cx={x(minDay)} cy={y(main.p50[minDay])} r="4.5" fill={main.p50[minDay] < 0 ? 'var(--red)' : 'var(--band)'} />
    </svg>
  )
}
