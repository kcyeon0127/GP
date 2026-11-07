// 거래내역 파일로 한 번에 등록 (입력 편의). 서버가 반복 거래를 찾아 후보로 돌려주면,
// 사장님은 체크만 하고 "등록"을 누른다. 저장은 기존 거래처·고정비·대출 등록 API를 그대로 쓴다.
import { useState, type ChangeEvent } from 'react'
import { api, md, type ApiError } from '../../api.ts'
import { won } from '../../data.ts'

type Kind = 'SALES' | 'PURCHASE' | 'FIXED_COST' | 'LOAN'
interface CandidateDto {
  name: string; direction: 'IN' | 'OUT'; kind: Kind; pay_cycle: 'WEEKLY' | 'MONTHLY' | 'QUARTERLY'; pay_day: number; amount: number
  months: string | null; count: number; dates: string[]; varies: boolean; already: boolean; same_as: string | null
}
interface ImportDto { rows: number; period: [string, string]; last_balance: { date: string; balance: number } | null; candidates: CandidateDto[] }
interface Row extends CandidateDto { on: boolean; id: string }

const KIND_KO: Record<Kind, string> = { SALES: '매출처(받을 돈)', PURCHASE: '매입처(줄 돈)', FIXED_COST: '고정비', LOAN: '대출 상환' }
const MAX_FILE = 5_000_000 // 서버 제한(ImportIn.text)과 같다
const WEEKDAY = ['', '월', '화', '수', '목', '금', '토', '일']

/** 주기·방향에 따라 등록할 수 있는 종류 (고정비는 매월·분기만, 분기는 고정비만) */
function kindsFor(c: CandidateDto): Kind[] {
  if (c.direction === 'IN') return ['SALES']
  if (c.pay_cycle === 'WEEKLY') return ['PURCHASE']
  if (c.pay_cycle === 'QUARTERLY') return ['FIXED_COST']
  return ['PURCHASE', 'FIXED_COST', 'LOAN']
}

function when(c: CandidateDto): string {
  if (c.pay_cycle === 'WEEKLY') return `매주 ${WEEKDAY[c.pay_day]}요일`
  const day = c.pay_day === 31 ? '말일' : `${c.pay_day}일`
  return c.pay_cycle === 'QUARTERLY' ? `${c.months}월 ${day}` : `매월 ${day}`
}

function bodyOf(r: Row): [string, Record<string, unknown>] {
  if (r.kind === 'SALES' || r.kind === 'PURCHASE') {
    return ['/api/counterparties', { name: r.name, trade_type: r.kind, pay_cycle: r.pay_cycle, pay_day: r.pay_day, amount: r.amount }]
  }
  if (r.kind === 'FIXED_COST') {
    return ['/api/fixed-costs', { name: r.name, pay_cycle: r.pay_cycle, pay_day: r.pay_day, amount: r.amount, months: r.months }]
  }
  // 대출 잔액·금리는 거래내역에 없어서 0으로 두고, 목록에서 수정해 채운다
  // (예상 잔액은 월 상환액만 쓰므로 0이어도 계산은 맞다. 고정금리로 두어 금리 시나리오에도 걸리지 않는다.)
  return ['/api/loans', { name: r.name, lender: r.name.split(' ')[0], principal: 0, interest_rate: 0, rate_type: 'FIXED', installment: r.amount, repay_day: r.pay_day }]
}

/** 은행 파일은 UTF-8 또는 EUC-KR(CP949)이다. UTF-8로 안 풀리면 EUC-KR로 읽는다. */
async function readText(file: File): Promise<string> {
  const buf = await file.arrayBuffer()
  try { return new TextDecoder('utf-8', { fatal: true }).decode(buf) } catch { return new TextDecoder('euc-kr').decode(buf) }
}

export default function ImportSection({ onSaved }: { onSaved: () => void }) {
  const [data, setData] = useState<ImportDto | null>(null)
  const [rows, setRows] = useState<Row[]>([])
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const set = (i: number, patch: Partial<Row>) => setRows((rs) => rs.map((r, j) => (j === i ? { ...r, ...patch } : r)))

  const onFile = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    setMsg(''); setErr(''); setData(null); setRows([])
    if (file.size > MAX_FILE) { setErr('파일이 너무 커요. 5MB 이하로 기간을 줄여 다시 받아 주세요.'); return }
    try {
      const d = await api<ImportDto>('/api/imports/transactions', { method: 'POST', body: { text: await readText(file) } })
      setData(d)
      setRows(d.candidates.map((c) => ({ ...c, on: !c.already, id: `${c.name}-${c.direction}` }))) // 이미 등록된 이름은 꺼 둔다: 눌러도 409로 막히거나 고정비가 두 번 잡힌다
    } catch (ex) { setErr((ex as ApiError).message) }
  }
  const register = async () => {
    setBusy(true)
    const done: string[] = []
    const skipped: string[] = []
    // 한 건씩 보낸다: 이름이 겹친 한 건이 막혀도 나머지는 등록하고, 무엇을 건너뛰었는지 알려 주기 위해서다.
    for (const r of rows.filter((x) => x.on)) {
      const [path, body] = bodyOf(r)
      try { await api(path, { method: 'POST', body }); done.push(r.name) } catch (ex) { skipped.push(`${r.name}(${(ex as ApiError).message})`) }
    }
    setBusy(false)
    const loans = rows.some((r) => r.on && r.kind === 'LOAN' && done.includes(r.name))
    setMsg(`${done.length}건을 등록했어요.${skipped.length ? ` 건너뛴 것: ${skipped.join(', ')}.` : ''}${loans ? ' 대출 잔액·금리는 아래 대출 목록에서 "수정"으로 채워 주세요.' : ''}`)
    setRows((rs) => rs.map((r) => (done.includes(r.name) ? { ...r, on: false, already: true } : r)))
    onSaved()
  }
  const setBalance = async () => {
    if (!data?.last_balance) return
    await api('/api/forecasts', { method: 'POST', body: { current_balance: data.last_balance.balance } })
    setMsg(`현재 잔액을 ${won(data.last_balance.balance)}(${md(data.last_balance.date)} 거래 후 잔액)으로 맞췄어요.`)
    onSaved()
  }
  const picked = rows.filter((r) => r.on).length

  return (
    <section className="card import">
      <h2>거래내역 파일로 한 번에 등록</h2>
      <p className="muted">인터넷뱅킹에서 받은 거래내역 CSV를 올리면, 매달·매주 반복되는 입출금을 찾아 드려요. 맞는 것만 체크해서 등록하세요.</p>
      <div className="import-pick">
        <label className="btn">파일 선택<input type="file" accept=".csv,text/csv" onChange={onFile} hidden /></label>
        <a className="link-btn" href="/sample_bank_transactions.csv" download>샘플 파일 받기</a>
      </div>
      {err && <p className="form-msg" role="alert">{err}</p>}
      {data && (
        <>
          <p className="sub">{md(data.period[0])}~{md(data.period[1])} 거래 {data.rows}건에서 정기 일정 <b>{rows.length}개</b>를 찾았어요.
            {data.last_balance && <button type="button" className="link-btn" onClick={setBalance}>현재 잔액을 {won(data.last_balance.balance)}으로 맞추기</button>}
          </p>
          {rows.length === 0 && <p className="muted">반복되는 입출금을 찾지 못했어요. 2달 이상 기간으로 다시 받아 보세요.</p>}
          <ul className="cands">
            {rows.map((r, i) => (
              <li key={r.id} className={r.on ? 'on' : ''}>
                <input type="checkbox" checked={r.on} aria-label={`${r.name} 등록`} onChange={(e) => set(i, { on: e.target.checked })} />
                <input className="cand-name" value={r.name} aria-label="이름" onChange={(e) => set(i, { name: e.target.value })} />
                <select value={r.kind} aria-label="종류" onChange={(e) => set(i, { kind: e.target.value as Kind })} disabled={kindsFor(r).length === 1}>
                  {kindsFor(r).map((k) => <option key={k} value={k}>{KIND_KO[k]}</option>)}
                </select>
                <span className="muted">{when(r)} · {r.count}회</span>
                <b className={`num ${r.direction === 'OUT' ? 'bad' : ''}`}>{r.varies ? '약 ' : ''}{r.direction === 'OUT' ? '-' : '+'}{won(r.amount)}</b>
                {r.already && <span className="pill soon">{r.same_as && r.same_as !== r.name ? `같은 일정 있음: ${r.same_as}` : '이미 등록됨'}</span>}
              </li>
            ))}
          </ul>
          {rows.length > 0 && <button className="btn" type="button" disabled={!picked || busy} onClick={register}>{busy ? '등록 중…' : `선택한 ${picked}건 등록`}</button>}
        </>
      )}
      {msg && <p className="ok-msg" role="status">{msg}</p>}
    </section>
  )
}
