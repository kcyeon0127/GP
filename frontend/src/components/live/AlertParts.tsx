// 조기경보 신호와 영향 일정 (US-05, T18)
import { useEffect, useState } from 'react'
import { api, md, type DriverDto, type ForecastDto } from '../../api.ts'
import { won } from '../../data.ts'
import { signalReason } from '../../live.ts'

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

