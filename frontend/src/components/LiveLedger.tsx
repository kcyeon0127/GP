// 내 거래·일정 등록 (US-01·02, T4·T8). 저장하면 서버가 12주 예정일을 만들어 돌려준다.
import { useEffect, useState, type FormEvent } from 'react'
import { api, ApiError, md, type CounterpartyDto, type FixedCostDto, type LoanDto } from '../api.ts'
import { won } from '../data.ts'

type Values = Record<string, string>
interface Field { name: string; label: string; type?: 'text' | 'number' | 'select'; options?: [string, string][]; placeholder?: string; optional?: boolean }

const CYCLE: [string, string][] = [['', '선택'], ['MONTHLY', '매월'], ['WEEKLY', '매주'], ['QUARTERLY', '분기']]
const FIELD_KO: Record<string, string> = { name: '이름', trade_type: '거래 유형', pay_cycle: '결제 주기', pay_day: '결제일', amount: '금액', lender: '금융기관', installment: '월 상환액', repay_day: '상환일', principal: '대출 잔액', interest_rate: '금리' }

function useForm(fields: Field[], submit: (body: Record<string, unknown>) => Promise<unknown>, onDone: () => void) {
  const blank = Object.fromEntries(fields.map((f) => [f.name, f.type === 'select' ? (f.options?.[0][0] ?? '') : '']))
  const [values, setValues] = useState<Values>(blank)
  const [bad, setBad] = useState<string[]>([])
  const [msg, setMsg] = useState('')
  const onSubmit = async (e: FormEvent) => {
    e.preventDefault()
    // 빈 칸은 보내지 않는다: 서버가 빠진 칸을 fields로 돌려준다 (AC: 저장 거부·빠진 칸 표시)
    const body = Object.fromEntries(Object.entries(values).filter(([, v]) => v !== '').map(([k, v]) => {
      const f = fields.find((x) => x.name === k)!
      return [k, f.type === 'number' ? Number(v) : v]
    }))
    try {
      await submit(body)
      setValues(blank); setBad([]); setMsg(''); onDone()
    } catch (err) {
      const ae = err as ApiError
      setBad(ae.fields ?? [])
      setMsg(ae.fields?.length ? `${ae.fields.map((x) => FIELD_KO[x] ?? x).join(', ')}을(를) 확인하세요. 금액은 0보다 커야 해요.` : ae.message)
    }
  }
  const render = (
    <>
      <div className="form-grid">
        {fields.map((f) => (
          <label key={f.name}>{f.label}{f.optional && ' (선택)'}
            {f.type === 'select' ? (
              <select className={bad.includes(f.name) ? 'invalid' : ''} value={values[f.name]} onChange={(e) => setValues({ ...values, [f.name]: e.target.value })}>
                {f.options!.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            ) : (
              <input className={bad.includes(f.name) ? 'invalid' : ''} type={f.type ?? 'text'} inputMode={f.type === 'number' ? 'numeric' : undefined}
                placeholder={f.placeholder} value={values[f.name]} aria-invalid={bad.includes(f.name)} onChange={(e) => setValues({ ...values, [f.name]: e.target.value })} />
            )}
          </label>
        ))}
        <button className="btn" type="submit">저장</button>
      </div>
      <p className="form-msg" role="alert">{msg}</p>
    </>
  )
  return { onSubmit, render }
}

const dates = (ds: string[]) => ds.length ? ds.slice(0, 3).map(md).join(', ') + (ds.length > 3 ? ` 외 ${ds.length - 3}회` : '') : '12주 안 예정 없음'

export default function LiveLedger() {
  const [cps, setCps] = useState<CounterpartyDto[]>([])
  const [fcs, setFcs] = useState<FixedCostDto[]>([])
  const [loans, setLoans] = useState<LoanDto[]>([])
  const load = () => {
    api<CounterpartyDto[]>('/api/counterparties').then(setCps)
    api<FixedCostDto[]>('/api/fixed-costs').then(setFcs)
    api<LoanDto[]>('/api/loans').then(setLoans)
  }
  useEffect(load, [])
  const del = (path: string) => api(path, { method: 'DELETE' }).then(load)

  const cpForm = useForm([
    { name: 'name', label: '거래처 이름', placeholder: '예: 한빛식자재' },
    { name: 'trade_type', label: '거래 유형', type: 'select', options: [['SALES', '매출처(받을 돈)'], ['PURCHASE', '매입처(줄 돈)']] },
    { name: 'pay_cycle', label: '결제 주기', type: 'select', options: CYCLE },
    { name: 'pay_day', label: '결제일', type: 'number', placeholder: '1~31 (매주는 요일 1~7)' },
    { name: 'amount', label: '금액(원)', type: 'number' },
  ], (b) => api('/api/counterparties', { method: 'POST', body: b }), load)
  const fcForm = useForm([
    { name: 'name', label: '고정비 이름', placeholder: '예: 임대료' },
    { name: 'pay_cycle', label: '주기', type: 'select', options: [['MONTHLY', '매월'], ['QUARTERLY', '분기']] },
    { name: 'pay_day', label: '지급일', type: 'number', placeholder: '1~31' },
    { name: 'amount', label: '금액(원)', type: 'number' },
    { name: 'payee', label: '받는 곳', placeholder: '예: 건물주', optional: true },
  ], (b) => api('/api/fixed-costs', { method: 'POST', body: b }), load)
  const loanForm = useForm([
    { name: 'name', label: '대출 이름', placeholder: '예: 운영자금대출' },
    { name: 'lender', label: '금융기관' },
    { name: 'installment', label: '월 원리금(원)', type: 'number' },
    { name: 'repay_day', label: '상환일', type: 'number', placeholder: '1~31' },
    { name: 'principal', label: '대출 잔액(원)', type: 'number' },
    { name: 'interest_rate', label: '금리(%)', type: 'number' },
    { name: 'rate_type', label: '금리 유형', type: 'select', options: [['FIXED', '고정'], ['VARIABLE', '변동']] },
  ], (b) => api('/api/loans', { method: 'POST', body: b }), load)

  return (
    <div className="stack">
      <section className="card">
        <h2>거래처·결제 조건 <span className="count">{cps.length}</span></h2>
        <form onSubmit={cpForm.onSubmit}>{cpForm.render}</form>
        {cps.map((c) => (
          <div className="row" key={c.counterparty_id}>
            <span>{c.name} <span className="muted">· {c.trade_type === 'SALES' ? '매출처' : '매입처'}</span><br /><span className="muted">예정일 {dates(c.next_due_dates)}</span></span>
            <span className="actions"><b className={`num ${c.trade_type === 'PURCHASE' ? 'bad' : ''}`}>{c.trade_type === 'PURCHASE' ? '-' : '+'}{won(c.amount)}</b>
              <button className="x-btn" onClick={() => del(`/api/counterparties/${c.counterparty_id}`)}>삭제</button></span>
          </div>
        ))}
      </section>
      <section className="card">
        <h2>고정비 <span className="count">{fcs.length}</span></h2>
        <form onSubmit={fcForm.onSubmit}>{fcForm.render}</form>
        {fcs.map((f) => (
          <div className="row" key={f.fixed_cost_id}>
            <span>{f.name}{f.payee && <span className="muted"> · {f.payee}</span>}<br /><span className="muted">예정일 {dates(f.next_due_dates)}</span></span>
            <span className="actions"><b className="num bad">-{won(f.amount)}</b><button className="x-btn" onClick={() => del(`/api/fixed-costs/${f.fixed_cost_id}`)}>삭제</button></span>
          </div>
        ))}
      </section>
      <section className="card">
        <h2>대출 상환 <span className="count">{loans.length}</span></h2>
        <form onSubmit={loanForm.onSubmit}>{loanForm.render}</form>
        {loans.map((l) => (
          <div className="row" key={l.loan_id}>
            <span>{l.name} <span className="muted">· {l.lender} · {l.rate_type === 'VARIABLE' ? '변동' : '고정'} {l.interest_rate}%</span><br /><span className="muted">상환일 {dates(l.next_due_dates)}</span></span>
            <span className="actions"><b className="num bad">-{won(l.installment)}</b><button className="x-btn" onClick={() => del(`/api/loans/${l.loan_id}`)}>삭제</button></span>
          </div>
        ))}
      </section>
    </div>
  )
}
