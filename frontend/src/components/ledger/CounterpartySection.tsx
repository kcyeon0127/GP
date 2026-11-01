// 거래처·결제 조건 등록 (US-01, T4)
import { api, type CounterpartyDto } from '../../api.ts'
import { won } from '../../data.ts'
import { CYCLE, dates, useForm } from './form.tsx'

export default function CounterpartySection({ items, reload }: { items: CounterpartyDto[]; reload: () => void }) {
  const del = (id: number) => api(`/api/counterparties/${id}`, { method: 'DELETE' }).then(reload)
  const f = useForm([
    { name: 'name', label: '거래처 이름', placeholder: '예: 한빛식자재' },
    { name: 'trade_type', label: '거래 유형', type: 'select', options: [['SALES', '매출처(받을 돈)'], ['PURCHASE', '매입처(줄 돈)']] },
    { name: 'pay_cycle', label: '결제 주기', type: 'select', options: CYCLE },
    { name: 'pay_day', label: '결제일', type: 'number', placeholder: '1~31 (매주는 요일 1~7)' },
    { name: 'amount', label: '금액(원)', type: 'number' },
  ], (b) => api('/api/counterparties', { method: 'POST', body: b }), reload)
  return (
    <section className="card">
      <h2>거래처·결제 조건 <span className="count">{items.length}</span></h2>
      <form onSubmit={f.onSubmit}>{f.render}</form>
      {items.map((c) => (
        <div className="row" key={c.counterparty_id}>
          <span>{c.name} <span className="muted">· {c.trade_type === 'SALES' ? '매출처' : '매입처'}</span><br /><span className="muted">예정일 {dates(c.next_due_dates)}</span></span>
          <span className="actions"><b className={`num ${c.trade_type === 'PURCHASE' ? 'bad' : ''}`}>{c.trade_type === 'PURCHASE' ? '-' : '+'}{won(c.amount)}</b>
            <button className="x-btn" onClick={() => del(c.counterparty_id)}>삭제</button></span>
        </div>
      ))}
    </section>
  )
}
