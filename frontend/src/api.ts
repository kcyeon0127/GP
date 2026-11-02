// 백엔드(FastAPI) 호출. VITE_API_URL이 없으면 http://localhost:8000을 쓴다.
// 서버에 닿지 않으면 화면은 합성 데이터 시연 버전으로 돌아간다(useApiStatus).
import { useEffect, useState } from 'react'

const BASE = (import.meta.env?.VITE_API_URL as string | undefined)?.replace(/\/$/, '') ?? 'http://localhost:8000'

export class ApiError extends Error {
  status: number
  fields: string[]
  constructor(status: number, message: string, fields: string[] = []) {
    super(message)
    this.status = status
    this.fields = fields
  }
}

export async function api<T>(path: string, init?: { method?: string; body?: unknown }): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: init?.method ?? 'GET',
    headers: init?.body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
    body: init?.body !== undefined ? JSON.stringify(init.body) : undefined,
  })
  if (res.status === 204) return undefined as T
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new ApiError(res.status, data.detail ?? `요청 실패 (${res.status})`, data.fields ?? [])
  return data as T
}

let cached: Promise<boolean> | null = null
export function apiAvailable(): Promise<boolean> {
  cached ??= fetch(`${BASE}/api/health`, { signal: AbortSignal.timeout(2500) }).then((r) => r.ok).catch(() => false)
  return cached
}

/** null = 확인 중, true = 서버 사용, false = 시연 데이터 */
export function useApiStatus(): boolean | null {
  const [ok, setOk] = useState<boolean | null>(null)
  useEffect(() => { apiAvailable().then(setOk) }, [])
  return ok
}

// ---------- 타입 (backend/app/schemas.py와 같은 모양) ----------
export type PayCycle = 'WEEKLY' | 'MONTHLY' | 'QUARTERLY'
export type SignalLevel = 'RED' | 'YELLOW' | 'GREEN'
export interface CounterpartyDto { counterparty_id: number; contract_id: number; name: string; trade_type: 'SALES' | 'PURCHASE'; pay_cycle: PayCycle; pay_day: number; amount: number; next_due_dates: string[] }
export interface FixedCostDto { fixed_cost_id: number; name: string; pay_cycle: 'MONTHLY' | 'QUARTERLY'; pay_day: number; months: string | null; amount: number; payee: string | null; next_due_dates: string[] }
export interface LoanDto { loan_id: number; name: string; lender: string; principal: number; interest_rate: number; rate_type: 'FIXED' | 'VARIABLE'; installment: number; repay_day: number; next_due_dates: string[] }
export interface ForecastDto {
  run_id: number; base_date: string; start_balance: number; safety_balance: number; signal: SignalLevel
  first_shortage_date: string | null; shortage_amount: number | null; max_shortage_amount: number | null
  min_balance: number; min_balance_date: string; first_below_safe_date: string | null; has_events: boolean; message: string
  daily?: { date: string; balance: number }[]
}
export interface DriverDto { cash_event_id: number; date: string; label: string; direction: 'IN' | 'OUT'; amount: number; role: 'BEFORE' | 'AFTER' }
export interface EvidenceDto { id: string; type: 'GRAPH_PATH' | 'DOCUMENT_CHUNK'; ref: string; text: string; score?: number }
export interface GraphDto { nodes: { id: string; label: string; props: Record<string, unknown> }[]; edges: { id: string; source: string; target: string; type: string }[] }

export const md = (iso: string) => `${+iso.slice(5, 7)}/${+iso.slice(8, 10)}`
