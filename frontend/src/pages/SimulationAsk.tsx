// 시나리오: 말로 물어보기 (US-18 D, US-09 조건). 질문을 백엔드 POST /api/ask에 보내고 결과만 그린다.
// 질문 해석(sLLM, 실패 시 규칙)·계산(ScenarioService)·경로 근거·설명 검증은 모두 백엔드가 한다. 화면은 숫자를 만들지 않는다.
// 백엔드에 닿지 않으면 시연 데이터로 대신 계산하지 않고 오류를 안내한다.
import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { CartesianGrid, ComposedChart, Legend, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, ApiError, md, type CounterpartyDto, type SignalLevel } from '../api.ts'
import { won } from '../data.ts'
import ConfidenceChip from '../components/grounded/ConfidenceChip.tsx'
import GroundedText, { EvidenceRows } from '../components/grounded/GroundedText.tsx'
import type { ConfidenceDto, ExplanationDto, GroundedEvidence } from '../components/grounded/types.ts'

interface Summary {
  signal: SignalLevel; first_shortage_date: string | null; shortage_amount: number | null
  min_balance: number; min_balance_date: string; daily: { date: string; balance: number }[]
}
interface AskDto {
  query: string
  plan: {
    source: 'llm' | 'rule'; fallback_reason: 'LLM_DOWN' | 'LLM_ERROR' | 'VERIFY_FAILED' | null
    described: string[]; recognized: string[]; problems: string[]
  }
  scenario_id?: number
  result: { base: Summary; scenario: Summary; new_shortages: { event_id: number; date: string; label: string; amount: number }[] } | null
  evidence: GroundedEvidence[]; explanation: ExplanationDto | null; confidence: ConfidenceDto | null; message: string | null
}

const SIGNAL = { RED: { cls: 'red', ko: '위험' }, YELLOW: { cls: 'yellow', ko: '주의' }, GREEN: { cls: 'green', ko: '안정' } } as const
const PLAN_FALLBACK = { LLM_DOWN: 'AI 서버 꺼짐', LLM_ERROR: 'AI 응답 오류', VERIFY_FAILED: 'AI 해석 검증 실패' } as const
const day = (d: string | null) => (d ? md(d) : '없음')

function AskChart({ base, scen }: { base: Summary; scen: Summary }) {
  const data = base.daily.map((d, i) => ({ date: d.date, base: d.balance, scenario: scen.daily[i]?.balance }))
  const vals = data.flatMap((d) => [d.base, d.scenario ?? 0])
  return (
    <div style={{ width: '100%', height: 260 }}>
      <ResponsiveContainer>
        <ComposedChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="var(--rule)" vertical={false} />
          <XAxis dataKey="date" tickFormatter={md} interval={13} tick={{ fontSize: 11, fill: 'var(--muted)' }} />
          <YAxis domain={[Math.min(0, ...vals), Math.max(0, ...vals)]} tickFormatter={(v: number) => `${Math.round(v / 10000)}만`} width={52} tick={{ fontSize: 11, fill: 'var(--muted)' }} />
          <Tooltip formatter={(v: number, n: string) => [won(v), n === 'base' ? '기준안' : '질문 조건']} labelFormatter={(l: string) => md(l)} />
          <Legend formatter={(v: string) => (v === 'base' ? '기준안' : '질문 조건')} />
          <ReferenceLine y={0} stroke="var(--ink)" strokeWidth={1.2} />
          <Line type="stepAfter" dataKey="base" stroke="var(--band)" strokeWidth={2} dot={false} isAnimationActive={false} />
          <Line type="stepAfter" dataKey="scenario" stroke="var(--red)" strokeWidth={2} dot={false} isAnimationActive={false} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}

/** 예시 질문은 실제 등록된 매출처 이름으로 만든다. */
function useExamples(): string[] {
  const [sales, setSales] = useState<string | null>(null)
  useEffect(() => {
    api<CounterpartyDto[]>('/api/counterparties').then((cs) => setSales(cs.find((c) => c.trade_type === 'SALES')?.name ?? null)).catch(() => setSales(null))
  }, [])
  return [
    ...(sales ? [`${sales} 정산이 2주 밀리면 대출 갚을 수 있어?`] : []),
    '다음 달 매출이 20% 줄면 어떻게 돼?',
    '원가가 10% 오르면 언제 모자라?',
    '금리가 1%p 오르면 상환 부담이 얼마나 늘어?',
  ]
}

export default function SimulationAsk() {
  const [params, setParams] = useSearchParams()
  const [query, setQuery] = useState('')
  const [busy, setBusy] = useState(false)
  const [out, setOut] = useState<AskDto | null>(null)
  const [err, setErr] = useState('')
  const [copied, setCopied] = useState(false)
  const examples = useExamples()

  const run = async (q: string) => {
    const text = q.trim()
    if (!text || busy) return
    setBusy(true); setCopied(false); setErr('')
    try {
      setOut(await api<AskDto>('/api/ask', { method: 'POST', body: { query: text } }))
    } catch (e) {
      setOut(null)
      setErr(e instanceof ApiError ? e.message : '서버에 연결되지 않았어요. 백엔드(머니메이트 API)를 켠 뒤 다시 시도하세요.')
    } finally { setBusy(false) }
  }

  // /simulation/ask?q=질문 으로 들어오면 바로 실행 (What-if 홈의 챗봇이 질문을 넘긴다)
  const urlQuery = params.get('q')
  useEffect(() => {
    if (urlQuery) { setQuery(urlQuery); void run(urlQuery) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [urlQuery])

  const submit = (q: string) => {
    const t = q.trim()
    if (!t) return
    if (t === urlQuery) void run(t)
    else setParams({ q: t }) // URL이 바뀌면 위 effect가 실행한다
  }

  const copy = async () => {
    if (!out?.explanation) return
    const body = `[질문] ${out.query}\n[가정] ${out.plan.described.join(', ')}\n[결과]\n${out.explanation.text}`
    try { await navigator.clipboard.writeText(body); setCopied(true) } catch { setCopied(false) }
  }

  const r = out?.result
  const sig = r ? SIGNAL[r.scenario.signal] : null
  return (
    <>
      <div className="page-head">
        <Link to="/simulation" className="back">← 시나리오</Link>
        <h1>시나리오: 말로 물어보기</h1>
      </div>

      <form className="card ask" onSubmit={(e) => { e.preventDefault(); submit(query) }}>
        <label htmlFor="q"><h2>궁금한 상황을 말로 물어보세요</h2></label>
        <p className="sub">등록한 거래처·정산·대출 일정으로 다시 계산하고, 금융지도 경로를 근거로 설명해 드려요. 정산 지연, 매출 감소, 원가 상승, 금리 상승을 계산할 수 있어요.</p>
        <div className="ask-row">
          <textarea id="q" rows={2} value={query} maxLength={300} placeholder={`예: ${examples[0]}`} onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit(query) } }} />
          <button className="btn" type="submit" disabled={busy || !query.trim()}>{busy ? '분석 중…' : '시뮬레이션'}</button>
        </div>
        <div className="chips" style={{ marginBottom: 0 }}>
          {examples.map((x) => <button type="button" key={x} onClick={() => { setQuery(x); submit(x) }}>{x}</button>)}
        </div>
      </form>

      {err && <div className="card" role="alert" style={{ marginTop: 18 }}><h2>질문을 계산하지 못했어요</h2><p className="sub" style={{ marginBottom: 0 }}>{err}</p></div>}

      {out && !r && (
        <div className="card" role="alert" style={{ marginTop: 18 }}>
          <h2>{out.message ?? '질문을 시뮬레이션으로 바꾸지 못했어요'}</h2>
          <ul style={{ margin: '8px 0 0' }}>{out.plan.problems.map((p) => <li key={p}>{p}</li>)}</ul>
          <p className="sub" style={{ marginTop: 10, marginBottom: 0 }}>거래처 이름, 기간, 비율을 함께 적어 주세요. 예: "{examples[0]}"</p>
        </div>
      )}

      {out && r && sig && (
        <div className="sim-grid" style={{ marginTop: 18 }}>
          <div className="stack">
            <div className="card">
              <div className="g-head">
                <h2>① 이해한 내용</h2>
                <span className={`g-badge ${out.plan.source === 'llm' ? 'ai' : 'base'}`}>
                  {out.plan.source === 'llm' ? 'AI 해석 · 조건 검증됨' : `규칙 해석${out.plan.fallback_reason ? ` (${PLAN_FALLBACK[out.plan.fallback_reason]})` : ''}`}
                </span>
              </div>
              <p className="sub" style={{ marginTop: 8 }}>질문을 시나리오 조건으로 바꿨어요.</p>
              {out.plan.described.map((d) => <div key={d} className="row"><span>{d}</span></div>)}
              {out.plan.recognized.length > 0 && <p className="muted small" style={{ marginTop: 8 }}>알아본 대상: {out.plan.recognized.join(' · ')}</p>}
              {out.plan.problems.length > 0 && <p className="notice">해석하지 못한 부분: {out.plan.problems.join(' ')}</p>}
            </div>
            <div className="card">
              <h2>② 금융지도에서 찾은 근거</h2>
              <p className="sub">조건으로 바뀌는 일정과 새로 모자라는 지급의 거래관계 경로예요. C1은 계산 모듈 결과예요.</p>
              {out.evidence.length === 0 && <p className="muted small">{out.message ?? '연결된 경로 근거가 없어요.'}</p>}
              <EvidenceRows items={out.evidence} calc={out.explanation?.calc ?? null} scope="ask" />
            </div>
          </div>

          <div className="stack">
            <div className={`signal ${sig.cls}`}>
              <span className="lamp" aria-hidden />
              <div><strong>질문 조건이면 자금 상태: {sig.ko}</strong>
                <p>{r.scenario.first_shortage_date ? `${md(r.scenario.first_shortage_date)}에 ${won(r.scenario.shortage_amount ?? 0)} 부족 예상` : '12주 안 부족 예상 없음'}</p></div>
            </div>
            <div className="card">
              <h2>③ 시뮬레이션 결과</h2>
              <div className="kpis" style={{ marginTop: 10 }}>
                <div className="kpi"><span>12주 최저 잔액</span><b className={`num ${r.scenario.min_balance < 0 ? 'bad' : ''}`}>{won(r.scenario.min_balance)}</b></div>
                <div className="kpi"><span>기준안 최저 잔액</span><b className="num">{won(r.base.min_balance)}</b></div>
                <div className="kpi"><span>최초 부족일</span><b className="num">{day(r.base.first_shortage_date)} → {day(r.scenario.first_shortage_date)}</b></div>
              </div>
              <AskChart base={r.base} scen={r.scenario} />
              {r.new_shortages.length > 0 && <p className="muted small">새로 모자라는 지급: {r.new_shortages.map((x) => `${md(x.date)} ${x.label}`).join(', ')}</p>}
            </div>
            <div className="card">
              <div className="g-head"><h2>④ 설명</h2>{out.confidence && <ConfidenceChip c={out.confidence} />}</div>
              {out.explanation && <div style={{ marginTop: 10 }}><GroundedText e={out.explanation} scope="ask" /></div>}
              {out.confidence?.level === 'LOW' && out.confidence.missing.length > 0 && <ul className="hold-list">{out.confidence.missing.map((m) => <li key={m}>{m}</li>)}</ul>}
              <div style={{ display: 'flex', gap: 10, marginTop: 12 }}>
                <button className="btn ghost" type="button" onClick={copy} disabled={!out.explanation}>{copied ? '복사됨' : '결과 요약 복사'}</button>
                <Link className="btn ghost" to="/simulation" style={{ textDecoration: 'none' }}>조건 직접 바꾸기</Link>
                {r.new_shortages.length > 0 && <Link className="btn" to="/agent" style={{ textDecoration: 'none' }}>대응안 보기</Link>}
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
