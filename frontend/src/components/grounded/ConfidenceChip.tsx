// 경보 신뢰도 칩 (US-18): 높음·보통·낮음. 누르면 이유와 무엇을 등록하면 올라가는지 펼친다.
import { useState } from 'react'
import type { ConfidenceDto } from './types.ts'
import './grounded.css'

const KO = { HIGH: '높음', MEDIUM: '보통', LOW: '낮음' } as const

export default function ConfidenceChip({ c, label = '신뢰도' }: { c: ConfidenceDto; label?: string }) {
  const [open, setOpen] = useState(false)
  return (
    <span className="g-conf-wrap">
      <button type="button" className={`g-conf ${c.level.toLowerCase()}`} aria-expanded={open} onClick={() => setOpen((v) => !v)}
        title={c.reasons.join('\n')}>
        {label} {KO[c.level]} <span className="g-score">{c.score}점</span>
      </button>
      {open && (
        <span className="g-conf-pop" role="note">
          <span className="g-conf-h">이렇게 판단했어요</span>
          <ul>{c.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
          {c.missing.length > 0 && <>
            <span className="g-conf-h">등록하면 신뢰도가 올라가요</span>
            <ul>{c.missing.map((m) => <li key={m}>{m}</li>)}</ul>
          </>}
          {c.level === 'LOW' && <span className="g-conf-note">신뢰도가 낮으면 대응안과 AI 설명을 보류해요.</span>}
        </span>
      )}
    </span>
  )
}
