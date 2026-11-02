// 등록·수정 폼 공통 (US-01·02): 빈 칸은 보내지 않고, 서버가 돌려준 빠진 칸(fields)을 빨갛게 표시한다.
// startEdit(id, 값)을 부르면 같은 폼이 수정 모드가 되어 저장 시 id와 함께 submit을 부른다.
import { useState, type FormEvent } from 'react'
import { md, type ApiError } from '../../api.ts'

export type Values = Record<string, string>
export interface Field { name: string; label: string; type?: 'text' | 'number' | 'select'; options?: [string, string][]; placeholder?: string; optional?: boolean }

export const CYCLE: [string, string][] = [['', '선택'], ['MONTHLY', '매월'], ['WEEKLY', '매주'], ['QUARTERLY', '분기']]
const FIELD_KO: Record<string, string> = { name: '이름', trade_type: '거래 유형', pay_cycle: '결제 주기', pay_day: '결제일', amount: '금액', lender: '금융기관', installment: '월 상환액', repay_day: '상환일', principal: '대출 잔액', interest_rate: '금리', months: '지급 월(1~12, 쉼표)', payee: '받는 곳' }

export function useForm(fields: Field[], submit: (body: Record<string, unknown>, id: number | null) => Promise<unknown>, onDone: () => void) {
  const blank = Object.fromEntries(fields.map((f) => [f.name, f.type === 'select' ? (f.options?.[0][0] ?? '') : '']))
  const [values, setValues] = useState<Values>(blank)
  const [bad, setBad] = useState<string[]>([])
  const [msg, setMsg] = useState('')
  const [editing, setEditing] = useState<number | null>(null)
  const reset = () => { setValues(blank); setBad([]); setMsg(''); setEditing(null) }
  const startEdit = (id: number, item: Record<string, unknown>) => {
    setValues(Object.fromEntries(fields.map((f) => [f.name, item[f.name] == null ? '' : String(item[f.name])])))
    setBad([]); setMsg(''); setEditing(id)
  }
  const onSubmit = async (e: FormEvent) => {
    e.preventDefault()
    // 빈 칸은 보내지 않는다: 서버가 빠진 칸을 fields로 돌려준다 (AC: 저장 거부·빠진 칸 표시)
    const body = Object.fromEntries(Object.entries(values).filter(([, v]) => v !== '').map(([k, v]) => {
      const f = fields.find((x) => x.name === k)!
      return [k, f.type === 'number' ? Number(v) : v]
    }))
    try {
      await submit(body, editing)
      reset(); onDone()
    } catch (err) {
      const ae = err as ApiError
      setBad(ae.fields ?? [])
      setMsg(ae.fields?.length ? `${ae.fields.map((x) => FIELD_KO[x] ?? x).join(', ')}을(를) 확인하세요.${ae.fields.includes('amount') ? ' 금액은 0보다 커야 해요.' : ''}` : ae.message)
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
        <button className="btn" type="submit">{editing === null ? '저장' : '수정 저장'}</button>
        {editing !== null && <button className="btn ghost" type="button" onClick={reset}>취소</button>}
      </div>
      <p className="form-msg" role="alert">{msg}</p>
    </>
  )
  return { onSubmit, render, startEdit, editing }
}

export const dates = (ds: string[]) => ds.length ? ds.slice(0, 3).map(md).join(', ') + (ds.length > 3 ? ` 외 ${ds.length - 3}회` : '') : '12주 안 예정 없음'

