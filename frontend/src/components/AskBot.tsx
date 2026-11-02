import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { EXAMPLES } from '../demo.ts'


// What-if 홈의 챗봇: 질문을 받으면 자연어 시뮬레이션 화면(/simulation/ask)으로 넘긴다.
export default function AskBot() {
  const [text, setText] = useState('')
  const nav = useNavigate()
  const go = (q: string) => {
    const t = q.trim()
    if (t) nav(`/simulation/ask?q=${encodeURIComponent(t)}`)
  }

  return (
    <section className="card bot" aria-labelledby="bot-h">
      <h2 id="bot-h">말로 물어보기</h2>
      <p className="sub">궁금한 상황을 입력하면 내 거래처·대출 정보를 근거로 시뮬레이션하고 설명해 드려요.</p>
      <div className="msg bot" style={{ maxWidth: '100%', marginBottom: 12 }}>
        어떤 상황이 걱정되세요? 예를 들어 정산이 늦어지거나, 매출이 줄거나, 금리가 오르는 경우를 물어볼 수 있어요.
      </div>
      <div className="chips" style={{ margin: '0 0 12px' }}>
        {EXAMPLES.map((x) => <button type="button" key={x} onClick={() => go(x)}>{x}</button>)}
      </div>
      <form className="bot-form" onSubmit={(e) => { e.preventDefault(); go(text) }}>
        <label htmlFor="bot-q" className="sr">질문 입력</label>
        <textarea id="bot-q" rows={2} value={text} placeholder="예: 한빛식자재 정산이 2주 밀리면?" onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); go(text) } }} />
        <button className="btn" type="submit" disabled={!text.trim()}>보내기</button>
      </form>
    </section>
  )
}
