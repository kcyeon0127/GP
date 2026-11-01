// 내 거래·일정 등록 (US-01). 저장하면 서버가 12주 예정일을 만들어 돌려준다.
import { useEffect, useState } from 'react'
import { api, type CounterpartyDto } from '../api.ts'
import CounterpartySection from './ledger/CounterpartySection.tsx'

export default function LiveLedger() {
  const [cps, setCps] = useState<CounterpartyDto[]>([])
  const load = () => { api<CounterpartyDto[]>('/api/counterparties').then(setCps) }
  useEffect(load, [])
  return (
    <div className="stack">
      <CounterpartySection items={cps} reload={load} />
    </div>
  )
}
