// 원인 보기: 서버가 있으면 등록 데이터로 만든 금융지도(US-06), 없으면 시연 지도(FinMap)를 보여 준다.
// US-08: 저장된 시나리오를 고르면 위험 영향 경로를 지도 위에 강조하고, 단계별 금액·날짜·근거 ID를 옆에 보여 준다.
import { useEffect, useState } from 'react'
import { Link, Navigate, useSearchParams } from 'react-router-dom'
import LiveMap from '../components/LiveMap.tsx'
import { api, md, useApiStatus, type ImpactPathDto, type PathStepDto, type ScenarioListDto } from '../api.ts'
import { won } from '../data.ts'

const KIND_KO: Record<string, string> = { SETTLEMENT_DELAY: '정산 지연', REVENUE_DROP: '매출 감소', COST_RISE: '원가 상승', RATE_RISE: '금리 상승' }
const ROLE_KO: Record<PathStepDto['role'], string> = { CAUSE: '원인', SHORTAGE: '부족', PAYMENT: '막히는 지급' }

function scenarioName(x: ScenarioListDto): string {
  const p = x.params
  const parts = x.kinds.map((k) => {
    if (k === 'SETTLEMENT_DELAY') return `정산 ${p.delay_days}일 지연`
    if (k === 'REVENUE_DROP') return `매출 -${p.revenue_drop_pct}%`
    if (k === 'COST_RISE') return `원가 +${p.cost_rise_pct}%`
    if (k === 'RATE_RISE') return `금리 +${p.rate_rise_pp}%p`
    return KIND_KO[k] ?? k
  })
  return `#${x.scenario_id} ${parts.join(' · ')}`
}

function stepLine(st: PathStepDto): string {
  if (st.role === 'CAUSE') return st.after_date && st.after_date !== st.date ? `${md(st.date)} → ${md(st.after_date)} · 잔액 영향 ${won(st.amount)}` : `${md(st.date)} · 잔액 영향 ${won(st.amount)}`
  if (st.role === 'SHORTAGE') return `${md(st.date)}~${md(st.end_date!)} · 첫날 부족액 ${won(st.amount)}`
  return `${md(st.date)} · ${won(st.amount)} · 그날 잔액 ${won(st.balance!)}`
}

function PathPanel({ path, selected, onSelect }: { path: ImpactPathDto | null; selected: number | null; onSelect: (i: number) => void }) {
  if (!path) return <div className="card"><h2>위험 영향 경로</h2><p className="sub" style={{ marginBottom: 0 }}>시나리오를 고르면 문제가 생긴 곳에서 어느 지급까지 영향이 이어지는지 지도에 표시해요.</p></div>
  const st = selected !== null ? path.steps[selected] : null
  return (
    <div className="card">
      <h2>위험 영향 경로</h2>
      <p className="sub">{path.message}</p>
      {path.steps.length > 0 && (
        <ol className="path-steps">
          {path.steps.map((s, i) => (
            <li key={i}>
              <button type="button" className={`path-step ${s.role.toLowerCase()} ${i === selected ? 'on' : ''}`} onClick={() => onSelect(i)}>
                <span className="path-no">{s.order ?? ROLE_KO[s.role]}</span>
                <span>{s.label}<br /><span className="muted">{stepLine(s)}</span></span>
              </button>
            </li>
          ))}
        </ol>
      )}
      {st && (
        <div className="path-detail" aria-live="polite">
          <div className="row"><span>단계</span><b>{st.order ? `${st.order}번째로 막히는 지급` : ROLE_KO[st.role]}</b></div>
          <div className="row"><span>금액</span><b className="num">{won(st.amount)}</b></div>
          <div className="row"><span>날짜</span><b>{st.role === 'SHORTAGE' ? `${md(st.date)}~${md(st.end_date!)}` : st.after_date && st.after_date !== st.date ? `${md(st.date)} → ${md(st.after_date)}` : md(st.date)}</b></div>
          <div className="row"><span>근거 ID</span><b>{st.evidence_id ?? '계산 결과 (잔액 0원 미만 구간)'}</b></div>
          {st.role === 'PAYMENT' && <div className="row"><span>기준안</span><b>{st.new ? '원래는 낼 수 있던 지급' : '원래도 부족했던 지급'}</b></div>}
        </div>
      )}
    </div>
  )
}

export default function MapPage() {
  const live = useApiStatus()
  const [params, setParams] = useSearchParams()
  const [key, setKey] = useState(0)
  const [msg, setMsg] = useState('')
  const [scenarios, setScenarios] = useState<ScenarioListDto[]>([])
  const [loaded, setLoaded] = useState<{ sid: string; data: ImpactPathDto | null } | null>(null)
  const [sel, setSel] = useState<{ sid: string | null; key: number; i: number } | null>(null)
  const scenarioId = params.get('scenario')

  useEffect(() => { if (live) api<ScenarioListDto[]>('/api/scenarios').then(setScenarios).catch(() => setScenarios([])) }, [live])
  useEffect(() => {
    if (!live || !scenarioId) return
    let alive = true
    api<ImpactPathDto>(`/api/scenarios/${scenarioId}/impact-path`)
      .then((d) => { if (alive) setLoaded({ sid: scenarioId, data: d }) })
      .catch((e) => { if (alive) { setLoaded({ sid: scenarioId, data: null }); setMsg(e.message) } })
    return () => { alive = false }
  }, [live, scenarioId, key])
  // 시나리오가 바뀌거나 지도를 다시 만들면 이전 경로·선택 단계는 보이지 않게 렌더 시점에 계산한다.
  const path = live && scenarioId && loaded?.sid === scenarioId ? loaded.data : null
  const selected = sel && sel.sid === scenarioId && sel.key === key ? sel.i : null
  const setSelected = (i: number) => setSel({ sid: scenarioId, key, i })

  if (live === null) return null
  if (!live) return <Navigate to="/map" replace />
  const sync = () => api<{ consistent: boolean; neo4j: Record<string, number> }>('/api/graph/sync', { method: 'POST' })
    .then((r) => { setMsg(r.consistent ? '금융지도를 다시 만들었어요. 노드 수가 원본 데이터와 일치해요.' : '노드 수가 원본과 다릅니다. 다시 시도하세요.'); setKey((k) => k + 1) })
  const choose = (v: string) => setParams(v ? { scenario: v } : {}, { replace: true })
  return (
    <>
      <div className="page-head">
        <Link to="/map" className="back">← 금융지도</Link>
        <h1 style={{ fontSize: 22 }}>내 등록 데이터 금융지도</h1>
      </div>
      <div className="row-head" style={{ marginBottom: 10 }}>
        <span className="muted">사업장을 가운데 두고 거래처·계약·고정비·대출의 연결을 보여 줘요. {msg}</span>
        <span style={{ display: 'flex', gap: 8 }}>
          <select aria-label="경로를 볼 시나리오" value={scenarioId ?? ''} onChange={(e) => choose(e.target.value)} style={{ width: 'auto', maxWidth: 260 }}>
            <option value="">시나리오 경로 끄기</option>
            {scenarios.map((x) => <option key={x.scenario_id} value={x.scenario_id}>{scenarioName(x)}</option>)}
          </select>
          <button className="btn ghost" onClick={sync}>금융지도 다시 만들기</button>
        </span>
      </div>
      <div className={scenarioId ? 'hub-grid' : ''}>
        <LiveMap key={key} path={path} selected={selected} onSelectStep={setSelected} />
        {scenarioId && <PathPanel path={path} selected={selected} onSelect={setSelected} />}
      </div>
    </>
  )
}
