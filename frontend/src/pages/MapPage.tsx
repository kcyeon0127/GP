// 원인 보기: 서버가 있으면 등록 데이터로 만든 금융지도(US-06), 없으면 시연 지도(FinMap)를 보여 준다.
import { useState } from 'react'
import { Link } from 'react-router-dom'
import LiveMap from '../components/LiveMap.tsx'
import { api, useApiStatus } from '../api.ts'
import FinMap from './FinMap.tsx'

export default function MapPage() {
  const live = useApiStatus()
  const [key, setKey] = useState(0)
  const [msg, setMsg] = useState('')
  if (live === null) return null
  if (!live) return <FinMap />
  const sync = () => api<{ consistent: boolean; neo4j: Record<string, number> }>('/api/graph/sync', { method: 'POST' })
    .then((r) => { setMsg(r.consistent ? '금융지도를 다시 만들었어요. 노드 수가 원본 데이터와 일치해요.' : '노드 수가 원본과 다릅니다. 다시 시도하세요.'); setKey((k) => k + 1) })
  return (
    <>
      <div className="page-head">
        <Link to="/" className="back">← 홈</Link>
        <h1 style={{ fontSize: 22 }}>원인 보기 · 거래관계 금융지도</h1>
      </div>
      <div className="row-head" style={{ marginBottom: 10 }}>
        <span className="muted">사업장을 가운데 두고 거래처·계약·고정비·대출의 연결을 보여 줘요. {msg}</span>
        <span style={{ display: 'flex', gap: 8 }}>
          <button className="btn ghost" onClick={sync}>금융지도 다시 만들기</button>
          <Link className="btn ghost" to="/map/demo">위험 전파 시연 <span className="pill soon">Sprint 2</span></Link>
        </span>
      </div>
      <LiveMap key={key} />
    </>
  )
}
