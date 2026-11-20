// 대응안 화면(LiveAgent)의 신뢰도·근거 인용 설명 (US-18). 대응안 응답(POST /api/response-plans)에 같이 온 값을 그린다.
import ConfidenceChip from './ConfidenceChip.tsx'
import GroundedText, { EvidenceRows } from './GroundedText.tsx'
import type { ConfidenceDto, ExplanationDto, GroundedEvidence } from './types.ts'
import './grounded.css'

export default function ProposalInsight({ confidence, explanation, evidence }: { confidence: ConfidenceDto | null; explanation: ExplanationDto | null; evidence: GroundedEvidence[] }) {
  if (!confidence && !explanation) return null
  const used = new Set(explanation?.cited_ids ?? [])
  return (
    <div className="card">
      <div className="g-head"><h2>왜 이 안인가요?</h2>{confidence && <ConfidenceChip c={confidence} label="경보 신뢰도" />}</div>
      {explanation && explanation.fallback_reason !== 'HOLD' && <>
        <div style={{ marginTop: 10 }}><GroundedText e={explanation} scope="plan" /></div>
        <EvidenceRows items={evidence.filter((e) => used.has(e.id))} calc={explanation.calc} scope="plan" />
      </>}
    </div>
  )
}
