// 고정비·대출 상환 일정 등록 (US-02, T8)
import { useEffect, useState } from 'react'
import { api, type FixedCostDto, type LoanDto } from '../../api.ts'
import { won } from '../../data.ts'
import { dates, useForm } from './form.tsx'

export default function FixedLoanSections() {
  const [fcs, setFcs] = useState<FixedCostDto[]>([])
  const [loans, setLoans] = useState<LoanDto[]>([])
  const load = () => {
    api<FixedCostDto[]>('/api/fixed-costs').then(setFcs)
    api<LoanDto[]>('/api/loans').then(setLoans)
  }
  useEffect(load, [])
  const del = (path: string) => api(path, { method: 'DELETE' }).then(load)
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
    <>
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
    </>
  )
}
