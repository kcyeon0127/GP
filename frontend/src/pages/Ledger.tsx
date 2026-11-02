import { Link } from 'react-router-dom'
import { business, monthlyEvents, dayLabel, partners, won, type EventKind } from '../data.ts'

// 내 거래·일정: 지금은 합성 데이터를 읽기 전용으로 보여 준다.
// 거래처·결제 조건 등록(US-01), 고정비·대출 등록(US-02), CSV 불러오기(US-03)가 이 화면에 들어온다.
const KIND: Record<EventKind, string> = { settlement: '정산(입금)', payable: '매입 대금', fixed: '고정비', loan: '대출 상환' }
const ROLE = { sales: '매출처', purchase: '매입처' } as const

const monthly = [...monthlyEvents].sort((a, b) => a.day - b.day)

export default function Ledger() {
  return (
    <>
      <div className="page-head">
        <Link to="/" className="back">← 홈</Link>
        <h1>내 거래·일정</h1>
      </div>
      <p className="muted" style={{ marginBottom: 16 }}>
        지금은 샘플 데이터입니다. 거래처·결제 조건 등록, 고정비·대출 등록, 거래내역 CSV 불러오기는 곧 추가됩니다. <span className="pill soon">US-01~03 예정</span>
      </p>
      <div className="stack">
        <section className="card">
          <h2>사업장</h2>
          <div className="row"><span>{business.name} · {business.industry}</span><span className="muted">{business.region}</span></div>
          <div className="row"><span>현재 잔액</span><b className="num">{won(business.startBalance)}</b></div>
          <div className="row"><span>안전 잔액 (이 아래로 내려가면 주의)</span><b className="num">{won(business.safeBalance)}</b></div>
        </section>
        <section className="card">
          <h2>거래처 <span className="count">{partners.length}</span></h2>
          {partners.map((p) => (
            <div className="row" key={p.id}><span>{p.name}</span><span className="muted">{ROLE[p.role]} · {p.taxStatus}</span></div>
          ))}
        </section>
        <section className="card">
          <h2>매달 반복되는 일정 <span className="count">{monthly.length}</span></h2>
          {monthly.map((e) => (
            <div className="row" key={e.id}>
              <span>{e.label}<br /><span className="muted">{KIND[e.kind]} · 매달 {dayLabel(e.day).split('/')[1]}일</span></span>
              <b className={`num ${e.direction === 'out' ? 'bad' : ''}`}>{e.direction === 'out' ? '-' : '+'}{won(e.amount)}</b>
            </div>
          ))}
        </section>
      </div>
    </>
  )
}
