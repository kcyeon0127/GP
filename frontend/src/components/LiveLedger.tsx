// 내 거래·일정 등록 (US-01·02). 저장하면 서버가 12주 예정일을 만들어 돌려준다.
// 저장·삭제할 때마다 예상 잔액을 다시 계산해 홈 최저 잔액이 얼마나 바뀌었는지 보여 준다.
import { useEffect, useRef, useState } from 'react'
import { api, md, type CounterpartyDto, type ForecastDto } from '../api.ts'
import { won } from '../data.ts'
import CounterpartySection from './ledger/CounterpartySection.tsx'
import FixedLoanSections from './ledger/FixedLoanSections.tsx'
import ImportSection from './ledger/ImportSection.tsx'

const SIGNAL_KO = { RED: '위험', YELLOW: '주의', GREEN: '안전' } as const

function impact(prev: ForecastDto, next: ForecastDto): string {
  const diff = next.min_balance - prev.min_balance
  const change = diff === 0 ? '그대로예요' : `${won(Math.abs(diff))} ${diff > 0 ? '올랐어요' : '내려갔어요'}`
  const sig = prev.signal === next.signal ? '' : ` 자금 상태도 ${SIGNAL_KO[prev.signal]} → ${SIGNAL_KO[next.signal]}로 바뀌었어요.`
  return `반영했어요. 12주 최저 잔액이 ${change} (${won(next.min_balance)}, ${md(next.min_balance_date)}).${sig}`
}

export default function LiveLedger() {
  const [cps, setCps] = useState<CounterpartyDto[]>([])
  const [note, setNote] = useState<{ text: string; worse: boolean } | null>(null)
  const [ver, setVer] = useState(0) // 파일로 여러 건 등록하면 고정비·대출 목록을 다시 불러온다
  const last = useRef<ForecastDto | null>(null)
  const forecast = () => api<ForecastDto>('/api/forecasts', { method: 'POST', body: {} })
  const onSaved = () => forecast().then((f) => {
    if (last.current) setNote({ text: impact(last.current, f), worse: f.min_balance < last.current.min_balance })
    last.current = f
  }).catch(() => setNote(null))
  const load = () => { api<CounterpartyDto[]>('/api/counterparties').then(setCps) }
  const reloadCps = () => { load(); onSaved() }
  useEffect(() => { load(); forecast().then((f) => { last.current = f }).catch(() => {}) }, [])
  return (
    <div className="stack">
      {note && <p className={`impact ${note.worse ? 'worse' : ''}`} role="status">{note.text}</p>}
      <ImportSection onSaved={() => { reloadCps(); setVer((v) => v + 1) }} />
      <CounterpartySection items={cps} reload={reloadCps} />
      <FixedLoanSections key={ver} onSaved={onSaved} />
    </div>
  )
}
