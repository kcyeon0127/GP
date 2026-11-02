// 서버 데이터 불러오기와 신호 문구 (홈 화면 서버 모드에서 쓴다)
import { useEffect, useState } from 'react'
import { api, md, type CounterpartyDto, type FixedCostDto, type ForecastDto, type LoanDto } from './api.ts'
import type { MiniStats } from './components/MiniMap.tsx'
import { won } from './data.ts'

export interface LiveEvent { key: string; label: string; date: string; amount: number; dir: 'IN' | 'OUT' }
export interface LiveData { f: ForecastDto; events: LiveEvent[]; stats: MiniStats }

/** 예상 잔액을 계산하고, 위젯·요약 지도에 쓸 등록 일정을 함께 불러온다. */
export function useLiveData() {
  const [data, setData] = useState<LiveData | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const load = (body: object = {}) =>
    Promise.all([
      api<ForecastDto>('/api/forecasts', { method: 'POST', body }),
      api<CounterpartyDto[]>('/api/counterparties'),
      api<FixedCostDto[]>('/api/fixed-costs'),
      api<LoanDto[]>('/api/loans'),
    ]).then(([f, cps, fcs, loans]) => {
      const events: LiveEvent[] = [
        ...cps.flatMap((c) => c.next_due_dates.map((d) => ({ key: `c${c.counterparty_id}-${d}`, label: `${c.name} ${c.trade_type === 'SALES' ? '정산' : '매입 대금'}`, date: d, amount: c.amount, dir: c.trade_type === 'SALES' ? 'IN' as const : 'OUT' as const }))),
        ...fcs.flatMap((x) => x.next_due_dates.map((d) => ({ key: `f${x.fixed_cost_id}-${d}`, label: x.name, date: d, amount: x.amount, dir: 'OUT' as const }))),
        ...loans.flatMap((l) => l.next_due_dates.map((d) => ({ key: `l${l.loan_id}-${d}`, label: `${l.name} 상환`, date: d, amount: l.installment, dir: 'OUT' as const }))),
      ].sort((a, b) => a.date.localeCompare(b.date))
      const sales = cps.filter((c) => c.trade_type === 'SALES')
      const outs = [...cps.filter((c) => c.trade_type === 'PURCHASE').map((c) => c.amount), ...fcs.map((x) => x.amount)]
      const stats: MiniStats = {
        balance: f.start_balance, partners: sales.length, inAmt: sales.reduce((a, c) => a + c.amount, 0),
        outCount: outs.length, outAmt: outs.reduce((a, b) => a + b, 0), loans: loans.length, loanAmt: loans.reduce((a, l) => a + l.installment, 0),
        cards: 0, contracts: cps.length + fcs.filter((x) => x.payee).length + loans.length, clauses: 0,
      }
      setData({ f, events, stats })
    }).catch((e) => setErr(e.message))
  useEffect(() => { load() }, [])
  return { data, err, reload: load }
}

export function signalReason(f: ForecastDto): string {
  if (f.signal === 'RED') return `${md(f.first_shortage_date!)}에 잔액이 0원 아래로 내려갑니다.`
  if (f.signal === 'YELLOW') return `${md(f.first_below_safe_date!)}에 잔액이 안전 잔액(${won(f.safety_balance)})보다 적어집니다.`
  return `4주 안에 잔액이 안전 잔액(${won(f.safety_balance)}) 아래로 내려가지 않습니다.`
}

