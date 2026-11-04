// "이유 보기" 근거 카드 (US-07, T28): 원래 "왜 자금 상태가 위험일까요?" 자리에 들어간다.
import { useState } from 'react'
import { api, type EvidenceDto, type ForecastDto } from '../../api.ts'
import { won } from '../../data.ts'
import { signalReason } from '../../live.ts'

/** 원래 "왜 자금 상태가 위험일까요?" 자리에 들어가는 근거 카드 (US-07 AC-02·03). */
export default function LiveWhy({ f }: { f: ForecastDto }) {
  const [ev, setEv] = useState<{ items: EvidenceDto[]; message: string | null } | null>(null)
  const level = f.signal === 'RED' ? '위험' : '주의'
  // 실패해도 버튼을 남긴다: 서버가 돌아오면 새로고침 없이 다시 누를 수 있게. 브라우저 오류 원문은 사장님에게 뜻이 없어 안내 문구로 바꾼다.
  const show = () => api<{ evidence: EvidenceDto[]; message: string | null }>(`/api/alerts/${f.run_id}/evidence`)
    .then((r) => setEv({ items: r.evidence, message: r.message }))
    .catch(() => setEv({ items: [], message: '근거를 불러오지 못했어요. 서버 연결을 확인한 뒤 다시 눌러 주세요.' }))
  return (
    <section className="why card" aria-labelledby="why-h">
      <div className="row-head"><h2 id="why-h">왜 자금 상태가 “{level}”일까요?</h2>{(!ev || !ev.items.length) && <button className="btn" onClick={show}>{ev ? '다시 보기' : '이유 보기'}</button>}</div>
      <p className="sub">{signalReason(f)} {f.shortage_amount ? `부족액 ${won(f.shortage_amount)}.` : ''}</p>
      {ev && (ev.items.length ? (
        <>
          <ol className="evidence">
            {ev.items.map((e) => <li key={e.id}><span className={`pill ${e.type === 'GRAPH_PATH' ? '' : 'soon'}`}>{e.id}</span> {e.text}</li>)}
          </ol>
          {ev.message && <p className="muted" role="status">{ev.message}</p>}
        </>
      ) : <p className="muted" role="status">{ev.message ?? '근거 없음'}</p>)}
      {ev && <p className="muted small">P = 거래관계 경로(금융지도), D = 계약 문서 조각. 금액은 계산 모듈 결과입니다.</p>}
    </section>
  )
}
