// 근거 인용 설명 (US-18): 문장 속 [P1]·[D1]·[C1]을 누를 수 있는 칩으로 바꾸고, 누가 썼는지 배지로 알린다.
import { highlight, type ExplanationDto } from './types.ts'
import './grounded.css'

const CITE = /(\[[A-Z]\d+(?:\s*[,·/]\s*[A-Z]\d+)*\])/g
const IS_CITE = /^\[[A-Z]\d+(?:\s*[,·/]\s*[A-Z]\d+)*\]$/

export function SourceBadge({ e }: { e: ExplanationDto }) {
  if (e.fallback_reason === 'HOLD') return <span className="g-badge hold">판단 보류</span>
  if (e.source === 'llm') return <span className="g-badge ai" title="sLLM이 쓴 문장을 근거 ID·숫자 검증을 통과한 뒤 보여 드려요">AI 작성 · 근거 확인됨</span>
  return <span className="g-badge base" title={e.problems.length ? `검증에서 걸린 부분: ${e.problems.join(' / ')}` : '같은 근거로 만든 기본 문장이에요'}>기본 문장 ({e.fallback_ko ?? '템플릿'})</span>
}

export default function GroundedText({ e, scope }: { e: ExplanationDto; scope: string }) {
  return (
    <div className="g-text">
      <p className="answer" aria-live="polite">
        {e.text.split(CITE).map((part, i) => {
          if (!IS_CITE.test(part)) return <span key={i}>{part}</span>
          return part.match(/[A-Z]\d+/g)!.map((id) => (
            <button type="button" key={`${i}-${id}`} className="ev cite" onClick={() => highlight(scope, id)} aria-label={`근거 ${id} 보기`}>{id}</button>
          ))
        })}
      </p>
      <SourceBadge e={e} />
    </div>
  )
}

/** 설명이 인용하는 근거 목록. 계산 결과(C1) 행을 마지막에 붙인다. */
export function EvidenceRows({ items, calc, scope }: { items: { id: string; type: string; text: string | null }[]; calc: ExplanationDto['calc']; scope: string }) {
  const rows = [...items, ...(calc ? [{ ...calc, type: 'CALCULATION' }] : [])]
  if (!rows.length) return null
  return (
    <ol className="evidence g-rows">
      {rows.map((x) => (
        <li key={x.id} id={`ev-${scope}-${x.id}`}>
          <span className={`pill ${x.type === 'GRAPH_PATH' ? '' : x.type === 'CALCULATION' ? 'green' : 'soon'}`}>{x.id}</span> {x.text ?? '근거'}
        </li>
      ))}
    </ol>
  )
}
