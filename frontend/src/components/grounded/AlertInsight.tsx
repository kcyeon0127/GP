// 경보 신뢰도·근거 인용 설명 (US-18). 홈 경보 영역(AlertConfidence)과 "이유 보기"(AlertExplain)에 붙인다.
// 설명 문장은 백엔드 explain_service가 만든다 (sLLM + 검증, 실패하면 같은 근거의 기본 문장). 화면은 숫자를 만들지 않는다.
import { useEffect, useState } from 'react'
import { api } from '../../api.ts'
import ConfidenceChip from './ConfidenceChip.tsx'
import GroundedText from './GroundedText.tsx'
import type { ConfidenceDto, ExplanationDto } from './types.ts'
import './grounded.css'

/** 홈 신호 옆 신뢰도 칩. LLM을 부르지 않는다. 안전(경보 없음)이거나 서버 오류면 아무것도 그리지 않는다. */
export function AlertConfidence({ runId }: { runId: number }) {
  const [c, setC] = useState<ConfidenceDto | null>(null)
  useEffect(() => {
    api<{ confidence: ConfidenceDto | null }>(`/api/alerts/${runId}/confidence`).then((r) => setC(r.confidence)).catch(() => setC(null))
  }, [runId])
  if (!c) return null
  return <div className="g-head" style={{ marginTop: -4 }}><span className="muted small">이 경보의 근거</span><ConfidenceChip c={c} /></div>
}

/** "이유 보기" 근거 목록 아래 설명. 칩을 누르면 같은 카드의 근거 행(id ev-alert-P1)을 강조한다. C1(계산 결과) 행은 여기서 붙인다. */
export function AlertExplain({ runId }: { runId: number }) {
  const [r, setR] = useState<{ explanation: ExplanationDto | null; confidence: ConfidenceDto | null } | null>(null)
  const [err, setErr] = useState(false)
  useEffect(() => {
    api<{ explanation: ExplanationDto | null; confidence: ConfidenceDto | null }>(`/api/alerts/${runId}/explain`, { method: 'POST' })
      .then(setR).catch(() => setErr(true))
  }, [runId])
  if (err) return <p className="muted small" role="status">설명을 불러오지 못했어요. 근거 목록은 위에서 확인할 수 있어요.</p>
  if (!r) return <p className="muted small" role="status">근거로 설명을 쓰는 중…</p>
  return (
    <div className="g-alert" style={{ display: 'grid', gap: 8, marginTop: 6 }}>
      <div className="g-head"><h3 style={{ fontSize: 15 }}>한 줄씩 근거를 붙인 설명</h3>{r.confidence && <ConfidenceChip c={r.confidence} />}</div>
      {r.explanation && <GroundedText e={r.explanation} scope="alert" />}
      {r.explanation?.calc && <p className="muted small" id="ev-alert-C1"><span className="pill green">C1</span> {r.explanation.calc.text}</p>}
      {r.confidence?.level === 'LOW' && r.confidence.missing.length > 0 && <ul className="hold-list">{r.confidence.missing.map((m) => <li key={m}>{m}</li>)}</ul>}
    </div>
  )
}
