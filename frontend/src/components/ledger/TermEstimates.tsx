// 결제조건 자동 추정 (US-14 T3): 올린 거래내역으로 매출처별 결제일·평균 지연일을 추정해 "추정"으로 보여 주고,
// 대표자가 고치거나 그대로 확정하면 저장한 뒤 예상 잔액을 다시 계산한다. 추정값은 확정 전까지 예측에 쓰지 않는다.
import { useEffect, useState } from 'react'
import { api, md, type ApiError } from '../../api.ts'
import { won } from '../../data.ts'

interface EstimateDto {
  name: string; status: 'ESTIMATED' | 'INSUFFICIENT' | 'IRREGULAR'; count: number; dates: string[]; amount: number
  counterparty_id: number | null; registered: { pay_cycle: string; pay_day: number } | null
  pay_cycle: 'WEEKLY' | 'MONTHLY' | null; pay_day: number | null; avg_delay_days: number | null; max_delay_days: number | null
  basis: string; confirmed_delay_days: number | null
}
interface Edit { day: string; delay: string }
const WEEKDAY = ['', '월', '화', '수', '목', '금', '토', '일']
const SIGNAL_KO: Record<string, string> = { RED: '위험', YELLOW: '주의', GREEN: '안전' }

export default function TermEstimates({ text, merges, refresh, onSaved }: { text: string; merges: Record<string, string>; refresh: number; onSaved: () => void }) {
  const [list, setList] = useState<EstimateDto[]>([])
  const [edit, setEdit] = useState<Record<string, Edit>>({})
  const [msg, setMsg] = useState('')
  useEffect(() => {
    if (!text) return
    api<{ estimates: EstimateDto[] }>('/api/payment-terms/estimate', { method: 'POST', body: { text, merges } }).then((d) => {
      setList(d.estimates)
      setEdit(Object.fromEntries(d.estimates.map((e) => [e.name, { day: String(e.pay_day ?? ''), delay: String(e.confirmed_delay_days ?? e.avg_delay_days ?? 0) }])))
    }).catch(() => setList([]))
  }, [text, merges, refresh])
  if (!list.length) return null
  const confirm = async (e: EstimateDto) => {
    const v = edit[e.name]
    try {
      const r = await api<{ pay_day: number; delay_days: number; forecast: { signal: string; first_shortage_date: string | null } }>(`/api/payment-terms/${e.counterparty_id}`, {
        method: 'PUT', body: { pay_cycle: e.pay_cycle, pay_day: +v.day, delay_days: +v.delay, sample_count: e.count },
      })
      setMsg(`${e.name} 결제조건을 확정했어요. 다시 계산한 4주 신호: ${SIGNAL_KO[r.forecast.signal]}${r.forecast.first_shortage_date ? ` (최초 부족일 ${md(r.forecast.first_shortage_date)})` : ''}.`)
      setList((xs) => xs.map((x) => (x.name === e.name ? { ...x, confirmed_delay_days: r.delay_days, registered: { pay_cycle: e.pay_cycle!, pay_day: r.pay_day } } : x)))
      onSaved()
    } catch (ex) { setMsg((ex as ApiError).message) }
  }
  const when = (cycle: string | null, day: number | null) => (cycle === 'WEEKLY' ? `매주 ${WEEKDAY[day ?? 0]}요일` : `매월 ${day}일`)
  return (
    <div className="terms">
      <h3>입금 패턴으로 추정한 결제조건 <span className="pill soon">추정</span></h3>
      <p className="sub">실제 입금 날짜를 보고 결제일과 평균 지연일을 추정했어요. 맞으면 확정하고, 다르면 고쳐서 확정하세요. 확정한 값만 예측에 써요.</p>
      {list.map((e) => (
        <div className="row term" key={e.name}>
          <span>
            <b>{e.name}</b> <span className="muted">약 {won(e.amount)} · 입금 {e.count}건</span>
            <br /><span className="muted">{e.basis}{e.registered ? ` · 등록: ${when(e.registered.pay_cycle, e.registered.pay_day)}` : ''}</span>
          </span>
          {e.status !== 'ESTIMATED' ? <span className="pill soon">{e.status === 'INSUFFICIENT' ? '거래 부족' : '불규칙'}</span>
            : !e.counterparty_id ? <span className="muted small">위 목록에서 먼저 등록하면 확정할 수 있어요</span>
            : (
              <span className="term-edit">
                <label>{e.pay_cycle === 'WEEKLY' ? '요일' : '결제일'} <input type="number" min={1} max={e.pay_cycle === 'WEEKLY' ? 7 : 31} value={edit[e.name]?.day ?? ''} aria-label={`${e.name} 결제일`} onChange={(ev) => setEdit((x) => ({ ...x, [e.name]: { ...x[e.name], day: ev.target.value } }))} /></label>
                <label>지연 <input type="number" min={0} max={60} value={edit[e.name]?.delay ?? ''} aria-label={`${e.name} 평균 지연일`} onChange={(ev) => setEdit((x) => ({ ...x, [e.name]: { ...x[e.name], delay: ev.target.value } }))} />일</label>
                <button type="button" className="btn ghost" onClick={() => confirm(e)}>{e.confirmed_delay_days !== null ? '다시 확정' : '확정'}</button>
              </span>
            )}
        </div>
      ))}
      {msg && <p className="ok-msg" role="status">{msg}</p>}
    </div>
  )
}
