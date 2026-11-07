// 등록·수정 폼 공통 (US-01·02): 빈 칸은 보내지 않고, 서버가 돌려준 빠진 칸(fields)을 빨갛게 표시한다.
// startEdit(id, 값)을 부르면 같은 폼이 수정 모드가 되어 저장 시 id와 함께 submit을 부른다.
// 입력 편의: 자주 쓰는 항목 버튼(presets), 금액 콤마·만원 표시(money), 주기에 맞는 날짜 칸(day).
import { useState, type FormEvent } from 'react'
import { md, type ApiError } from '../../api.ts'
import { won } from '../../data.ts'

export type Values = Record<string, string>
export interface Field {
  name: string; label: string; type?: 'text' | 'number' | 'select' | 'money' | 'day'; options?: [string, string][]; placeholder?: string; optional?: boolean
  /** type 'day': 이 칸의 값이 WEEKLY면 요일 선택, 아니면 1~31일과 '말일' 버튼 */
  cycleField?: string
}
export interface Preset { label: string; values: Values }

export const CYCLE: [string, string][] = [['', '선택'], ['MONTHLY', '매월'], ['WEEKLY', '매주'], ['QUARTERLY', '분기']]
const WEEKDAYS: [string, string][] = [['', '요일 선택'], ['1', '월요일'], ['2', '화요일'], ['3', '수요일'], ['4', '목요일'], ['5', '금요일'], ['6', '토요일'], ['7', '일요일']]
const LAST_DAY = '31' // 31일은 30일까지 있는 달에 말일로 맞춰진다 (US-01 AC-03)
const FIELD_KO: Record<string, string> = { name: '이름', trade_type: '거래 유형', pay_cycle: '결제 주기', pay_day: '결제일', amount: '금액', lender: '금융기관', installment: '월 상환액', repay_day: '상환일', principal: '대출 잔액', interest_rate: '금리', months: '지급 월(1~12, 쉼표)', payee: '받는 곳' }

// 금액 칸은 값을 숫자만으로 들고 콤마는 표시할 때만 붙인다. type="number"는 콤마를 넣을 수 없어 text로 둔다.
const digits = (v: string) => v.replace(/[^\d]/g, '')
const comma = (v: string) => (v ? Number(v).toLocaleString('ko-KR') : '')

export function useForm(fields: Field[], submit: (body: Record<string, unknown>, id: number | null) => Promise<unknown>, onDone: () => void) {
  const blank = Object.fromEntries(fields.map((f) => [f.name, f.type === 'select' ? (f.options?.[0][0] ?? '') : '']))
  const [values, setValues] = useState<Values>(blank)
  const [bad, setBad] = useState<string[]>([])
  const [msg, setMsg] = useState('')
  const [editing, setEditing] = useState<number | null>(null)
  const set = (name: string, v: string) => setValues((cur) => {
    const next = { ...cur, [name]: v }
    // 매주와 다른 주기를 오가면 날짜 칸을 비운다: 매월 5일의 5가 그대로 금요일이 되는 일을 막는다
    for (const f of fields) {
      if (f.cycleField === name && (cur[name] === 'WEEKLY') !== (v === 'WEEKLY')) next[f.name] = ''
    }
    return next
  })
  const reset = () => { setValues(blank); setBad([]); setMsg(''); setEditing(null) }
  const startEdit = (id: number, item: Record<string, unknown>) => {
    setValues(Object.fromEntries(fields.map((f) => [f.name, item[f.name] == null ? '' : String(item[f.name])])))
    setBad([]); setMsg(''); setEditing(id)
  }
  // blank에서 시작한다: 쓰던 값이나 앞서 누른 버튼의 값(부가세의 지급 월 등)이 다음 항목에 섞여 저장되지 않게.
  const applyPreset = (p: Preset) => { setValues({ ...blank, ...p.values }); setBad([]); setMsg(''); setEditing(null) }
  const onSubmit = async (e: FormEvent) => {
    e.preventDefault()
    // 빈 칸은 보내지 않는다: 서버가 빠진 칸을 fields로 돌려준다 (AC: 저장 거부·빠진 칸 표시)
    const body = Object.fromEntries(Object.entries(values).filter(([, v]) => v !== '').map(([k, v]) => {
      const f = fields.find((x) => x.name === k)!
      return [k, f.type === 'number' || f.type === 'money' || f.type === 'day' ? Number(v) : v]
    }))
    try {
      await submit(body, editing)
      reset(); onDone()
    } catch (err) {
      const ae = err as ApiError
      setBad(ae.fields ?? [])
      // 안내 문구는 이 폼의 칸 이름을 그대로 쓴다 (고정비는 '지급일', 거래처는 '결제일')
      const label = (x: string) => fields.find((f) => f.name === x)?.label ?? FIELD_KO[x] ?? x
      setMsg(ae.fields?.length ? `빨간 칸을 확인해 주세요: ${ae.fields.map(label).join(', ')}.${ae.fields.includes('amount') ? ' 금액은 0보다 커야 해요.' : ''}` : ae.message)
    }
  }
  const input = (f: Field) => {
    const cls = bad.includes(f.name) ? 'invalid' : ''
    const v = values[f.name]
    if (f.type === 'select') {
      return <select className={cls} value={v} onChange={(e) => set(f.name, e.target.value)}>{f.options!.map(([o, l]) => <option key={o} value={o}>{l}</option>)}</select>
    }
    if (f.type === 'money') {
      return <input className={cls} type="text" inputMode="numeric" placeholder={f.placeholder} value={comma(v)} aria-invalid={bad.includes(f.name)}
        onChange={(e) => set(f.name, digits(e.target.value))} />
    }
    if (f.type === 'day' && f.cycleField && values[f.cycleField] === 'WEEKLY') {
      return <select className={cls} value={v} onChange={(e) => set(f.name, e.target.value)}>{WEEKDAYS.map(([o, l]) => <option key={o} value={o}>{l}</option>)}</select>
    }
    if (f.type === 'day') {
      const last = v === LAST_DAY // 말일이면 숫자 칸을 비운다: "31일"로 보이면 2월·4월에는 어떻게 되는지 헷갈린다
      return (
        <span className="day-input">
          <input className={cls} type="number" inputMode="numeric" min={1} max={31} placeholder={f.placeholder ?? '1~31'} value={last ? '' : v} aria-invalid={bad.includes(f.name)}
            onChange={(e) => set(f.name, e.target.value)} />
          <button type="button" className={`chip ${last ? 'on' : ''}`} aria-pressed={last} onClick={() => set(f.name, last ? '' : LAST_DAY)}>말일</button>
        </span>
      )
    }
    return <input className={cls} type={f.type ?? 'text'} inputMode={f.type === 'number' ? 'numeric' : undefined} placeholder={f.placeholder} value={v} aria-invalid={bad.includes(f.name)}
      onChange={(e) => set(f.name, e.target.value)} />
  }
  const render = (presets: Preset[] = []) => (
    <>
      {/* 수정 중에는 숨긴다: 누르면 수정 모드가 풀려 새 항목으로 저장되기 때문이다 */}
      {presets.length > 0 && editing === null && (
        <div className="preset-row" aria-label="자주 쓰는 항목">
          <span className="muted">자주 쓰는 항목</span>
          {presets.map((p) => <button type="button" className="chip" key={p.label} onClick={() => applyPreset(p)}>{p.label}</button>)}
        </div>
      )}
      <div className="form-grid">
        {fields.map((f) => (
          <label key={f.name}>
            <span>{f.label}{f.optional && ' (선택)'}{f.type === 'money' && values[f.name] && <span className="hint"> · {won(Number(values[f.name]))}</span>}</span>
            {input(f)}
          </label>
        ))}
        <button className="btn" type="submit">{editing === null ? '저장' : '수정 저장'}</button>
        {editing !== null && <button className="btn ghost" type="button" onClick={reset}>취소</button>}
      </div>
      <p className="form-msg" role="alert">{msg}</p>
    </>
  )
  return { onSubmit, render, startEdit, editing }
}

export const dates = (ds: string[]) => ds.length ? ds.slice(0, 3).map(md).join(', ') + (ds.length > 3 ? ` 외 ${ds.length - 3}회` : '') : '12주 안 예정 없음'
