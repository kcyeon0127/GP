import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import BalanceChart from '../components/BalanceChart.tsx'
import Signal from '../components/Signal.tsx'
import { applyShocks, base, compare, forecast, signalOf, type Diff, type Forecast, type Shock, type Signal as Level } from '../engine.ts'
import { dayLabel, won } from '../data.ts'
import { describeShock, planQuery, type Plan } from '../planner.ts'
import { retrieve, type Evidence } from '../graphrag.ts'
import { explain, resultEvidence, type Explanation } from '../explain.ts'
import { EXAMPLES } from '../demo.ts'


interface Outcome {
  query: string
  plan: Plan
  shocks: Shock[]
  evidence: Evidence[]
  f: Forecast
  diff: Diff
  level: Level
  reason: string
  explanation: Explanation
}

export default function SimulationAsk() {
  const [params, setParams] = useSearchParams()
  const [query, setQuery] = useState('')
  const [busy, setBusy] = useState(false)
  const [outcome, setOutcome] = useState<Outcome | null>(null)
  const [failed, setFailed] = useState<Plan | null>(null)
  const [copied, setCopied] = useState(false)

  const run = async (q: string) => {
    const text = q.trim()
    if (!text || busy) return
    setBusy(true)
    setCopied(false)
    try {
      const plan = await planQuery(text) // S2: 질문 → 충격 계획
      if (plan.shocks.length === 0) {
        setFailed(plan)
        setOutcome(null)
        return
      }
      setFailed(null)
      const { evidence } = retrieve(plan.shocks) // Graph RAG: 사용자 상황·상품 근거 수집
      const st = applyShocks(plan.shocks) // M5/M4: 계산은 엔진이
      const f = forecast(st)
      const diff = compare(base.forecast, f, st.events)
      const sig = signalOf(f)
      const all = [...evidence, ...resultEvidence(evidence.length + 1, plan.shocks, base.forecast, f, diff, sig.level)]
      const explanation = await explain(text, all) // LLM 추론 + M9 검증
      setOutcome({ query: text, plan, shocks: plan.shocks, evidence: all, f, diff, level: sig.level, reason: sig.reason, explanation })
    } finally {
      setBusy(false)
    }
  }

  // /simulation/ask?q=질문 으로 들어오면 바로 실행 (What-if 홈의 챗봇이 질문을 넘긴다)
  const urlQuery = params.get('q')
  useEffect(() => {
    if (urlQuery) {
      setQuery(urlQuery)
      void run(urlQuery)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [urlQuery])

  const submit = (q: string) => {
    const t = q.trim()
    if (!t) return
    if (t === urlQuery) void run(t)
    else setParams({ q: t }) // URL이 바뀌면 위 effect가 실행한다. 새로고침해도 같은 결과가 나온다.
  }

  const copy = async () => {
    if (!outcome) return
    const body = `[질문] ${outcome.query}\n[가정] ${outcome.shocks.map(describeShock).join(', ')}\n[결과]\n${outcome.explanation.text}`
    try {
      await navigator.clipboard.writeText(body)
      setCopied(true)
    } catch {
      setCopied(false)
    }
  }

  return (
    <>
      <div className="page-head">
        <Link to="/simulation" className="back">← 시나리오</Link>
        <h1>시나리오: 말로 물어보기 <span className="pill soon">확장 예정</span></h1>
      </div>

      <form className="card ask" onSubmit={(e) => { e.preventDefault(); submit(query) }}>
        <label htmlFor="q"><h2>궁금한 상황을 말로 물어보세요</h2></label>
        <p className="sub">내 거래처·정산·대출 정보와 금융상품 정보를 근거로 어떻게 되는지 알려드려요.</p>
        <div className="ask-row">
          <textarea id="q" rows={2} value={query} placeholder="예: 한빛식자재 정산이 2주 밀리면 대출 갚을 수 있어?" onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit(query) } }} />
          <button className="btn" type="submit" disabled={busy || !query.trim()}>{busy ? '분석 중…' : '시뮬레이션'}</button>
        </div>
        <div className="chips" style={{ marginBottom: 0 }}>
          {EXAMPLES.map((x) => <button type="button" key={x} onClick={() => { setQuery(x); submit(x) }}>{x}</button>)}
        </div>
      </form>

      {failed && (
        <div className="card" role="alert" style={{ marginTop: 18 }}>
          <h2>질문을 시뮬레이션으로 바꾸지 못했습니다</h2>
          <ul style={{ margin: '8px 0 0' }}>{failed.problems.map((p) => <li key={p}>{p}</li>)}</ul>
          <p className="sub" style={{ marginTop: 10, marginBottom: 0 }}>거래처 이름, 기간, 금액을 함께 적어 주세요. 예: "{EXAMPLES[0]}"</p>
        </div>
      )}

      {outcome && (
        <div className="sim-grid" style={{ marginTop: 18 }}>
          <div className="stack">
            <div className="card">
              <h2>① 이해한 내용</h2>
              <p className="sub">질문에서 거래처·기간·금액을 찾아 시뮬레이션 조건으로 바꿨어요.</p>
              {outcome.shocks.map((k, i) => (
                <div key={i} className="row"><span>{describeShock(k)}</span></div>
              ))}
              {outcome.plan.problems.length > 0 && <p className="notice">해석하지 못한 부분: {outcome.plan.problems.join(' ')}</p>}
            </div>
            <div className="card">
              <h2>② 그래프에서 찾은 근거</h2>
              <p className="sub">내 상황과 상품 정보에서 이 질문과 연결된 항목입니다.</p>
              <ol className="evlist">
                {outcome.evidence.map((e) => (
                  <li key={e.id} id={`ev-${e.id}`}>
                    <span className={`ev ${e.kind}`}>{e.id}</span> {e.text}
                  </li>
                ))}
              </ol>
            </div>
          </div>

          <div className="stack">
            <Signal level={outcome.level} reason={outcome.reason} />
            <div className="card">
              <h2>③ 시뮬레이션 결과</h2>
              <div className="kpis" style={{ marginTop: 10 }}>
                <div className="kpi"><span>예상 최저 잔액</span><b className={`num ${outcome.f.minP50 < 0 ? 'bad' : ''}`}>{won(outcome.f.minP50)}</b></div>
                <div className="kpi"><span>기준선 대비</span><b className={`num ${outcome.diff.minP50Delta < 0 ? 'bad' : 'good'}`}>{outcome.diff.minP50Delta >= 0 ? '+' : ''}{won(outcome.diff.minP50Delta)}</b></div>
                <div className="kpi"><span>첫 부족 예상일</span><b className="num">{outcome.diff.firstShortAfter ? dayLabel(outcome.diff.firstShortAfter) : '없음'}</b></div>
              </div>
              <BalanceChart base={base.forecast} scenario={outcome.f} />
              <div className="legend">
                <span><i style={{ background: 'var(--band)' }} />기준선</span>
                <span><i style={{ background: 'var(--red)' }} />시나리오</span>
                <span>점선: 잔액 0원</span>
              </div>
            </div>
            <div className="card">
              <h2>④ 설명</h2>
              <div className="answer" aria-live="polite">{outcome.explanation.text.split(/(\[E\d+\])/g).map((part, i) => {
                const m = part.match(/^\[(E\d+)\]$/)
                return m ? <a key={i} className="ev" href={`#ev-${m[1]}`}>{m[1]}</a> : <span key={i}>{part}</span>
              })}</div>
              {outcome.explanation.note && <p className="notice">{outcome.explanation.note}</p>}
              <div style={{ display: 'flex', gap: 10, marginTop: 12 }}>
                <button className="btn ghost" type="button" onClick={copy}>{copied ? '복사됨' : '결과 요약 복사'}</button>
                {outcome.diff.newlyRisky.length > 0 && <Link className="btn" to="/agent" style={{ textDecoration: 'none' }}>대응안 보기</Link>}
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
