import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { applyShocks, forecast, signalOf, type Shock } from '../engine.ts'
import { dayLabel, won } from '../data.ts'
import { isRisk } from '../demo.ts'

// 위기 시나리오: 한빛식자재 정산 14일 지연. 대응안의 효과는 모두 엔진이 계산한다(M10).
const CRISIS: Shock = { type: 'settlement_delay', partnerId: 'P1', days: 14 }

interface Plan { id: string; title: string; how: string; shocks: Shock[]; cost: string }
const PLANS: Plan[] = [
  { id: 'A1', title: '한빛식자재에 정산 기일 앞당김 요청', how: '지연 14일 중 10일을 앞당겨 받습니다.', shocks: [{ type: 'settlement_delay', partnerId: 'P1', days: -10 }], cost: '비용 없음 · 거래처 협의 필요' },
  { id: 'A2', title: '대성유통 매입 대금 1차 지급 연기', how: '8일 지급분을 14일 늦춥니다.', shocks: [{ type: 'payable_defer', eventId: 'Y1', days: 14 }], cost: '거래 신뢰 영향 가능' },
  { id: 'A3', title: '임대료 지급일 이동', how: '5일 지급분을 7일 늦춥니다.', shocks: [{ type: 'cost_shift', eventId: 'F1', days: 7 }], cost: '임대인 협의 필요' },
  { id: 'A4', title: '발주량 30% 축소', how: '매입 대금 전체를 30% 줄입니다.', shocks: [{ type: 'payable_cut', pct: 30 }], cost: '매출 기회 감소 가능' },
  { id: 'A5', title: '정책 대출 검토 (500만원, 12개월)', how: '3일에 입금, 26일부터 월 상환이 시작됩니다.', shocks: [{ type: 'new_loan', amount: 5_000_000, ratePct: 3.0, months: 12 }], cost: '이자 연 3.0% · 비교 정보이며 권유가 아닙니다' },
]

interface Msg { who: 'user' | 'bot'; text: string }
const CHIPS = isRisk ? ['지금 자금 상황이 어때?', '부족하면 뭘 해야 해?', '정책대출을 받으면 해소될까?'] : ['다음 달 자금 괜찮을까?', '한빛식자재 정산이 2주 밀리면?', '부족하면 뭘 해야 해?']

export default function Agent() {
  const analysis = useMemo(() => {
    const crisisState = applyShocks(isRisk ? [] : [CRISIS]) // 위험 데모는 기준선이 이미 위기 상황이다
    const crisis = forecast(crisisState)
    const ranked = PLANS.map((p) => {
      const f = forecast(applyShocks(p.shocks, crisisState))
      return { ...p, f, gain: f.minP50 - crisis.minP50, solved: f.minP50 >= 0 }
    }).sort((a, b) => b.gain - a.gain)
    return { crisis, ranked }
  }, [])
  const { crisis, ranked } = analysis
  const sig = signalOf(crisis)

  const answer = (q: string): Msg => {
    if (isRisk && q.includes('정책')) {
      const a5 = ranked.find((r) => r.id === 'A5')!
      return { who: 'bot', text: `정책 대출 500만원(연 3.0%, 12개월)을 검토하면 최저 잔액이 ${won(crisis.minP50)}에서 ${won(a5.f.minP50)}가 되어 부족이 ${a5.solved ? '해소됩니다' : '일부만 줄어듭니다'}. 다만 비교 정보이며 권유가 아니고, 26일부터 월 상환이 시작됩니다.` }
    }
    if (isRisk && (q.includes('지금') || q.includes('상황'))) {
      return { who: 'bot', text: `한빛식자재 정산이 14일 늦어지는 것으로 확정되어 ${crisis.firstShortDay ? dayLabel(crisis.firstShortDay) : '곧'}부터 잔액이 부족합니다. ${dayLabel(crisis.minDay)} 전후 최저 잔액은 ${won(crisis.minP50)}이고, 인건비·공과금·운영자금대출 상환일이 모두 위험합니다.` }
    }
    if (q.includes('2주') || q.includes('밀리')) {
      return { who: 'bot', text: `한빛식자재 정산이 14일 늦어지면 ${dayLabel(crisis.minDay)} 전후 잔액이 ${won(crisis.minP50)}까지 내려갑니다. 첫 부족 예상일은 ${crisis.firstShortDay ? dayLabel(crisis.firstShortDay) : '없음'}이고, 운영자금대출 상환일에도 부족 위험이 큽니다.` }
    }
    if (q.includes('뭘') || q.includes('해야')) {
      const t = ranked[0]
      return { who: 'bot', text: `계산된 대응안 중 효과가 가장 큰 것은 "${t.title}"입니다. 최저 잔액이 ${won(t.gain)}만큼 개선됩니다. 오른쪽 목록에서 다른 안과 비교해 보세요.` }
    }
    return { who: 'bot', text: `기준 상태로는 4주 안에 부족 신호가 없지만 여유가 크지 않습니다. 주요 거래처 정산이 늦어지는 경우를 가정해 보려면 "한빛식자재 정산이 2주 밀리면?"을 눌러 보세요.` }
  }

  const [msgs, setMsgs] = useState<Msg[]>([{ who: 'bot', text: isRisk ? `안녕하세요. 지금 자금 상태는 "위험"입니다. 한빛식자재 정산이 14일 늦어지는 것으로 확정되어 ${crisis.firstShortDay ? dayLabel(crisis.firstShortDay) : ''}부터 잔액이 부족해요. 오른쪽에 효과가 계산된 대응안을 순위로 정리했습니다.` : `안녕하세요. 현재 가정한 위기 상황(한빛식자재 정산 14일 지연)에서 자금 상태는 "${sig.level === 'red' ? '위험' : '주의'}"입니다. 오른쪽에 효과가 계산된 대응안을 순위로 정리했습니다.` }])
  const [text, setText] = useState('')
  const send = (q: string) => {
    if (!q.trim()) return
    setMsgs((m) => [...m, { who: 'user', text: q }, answer(q)])
    setText('')
  }

  return (
    <>
      <div className="page-head">
        <Link to="/" className="back">← 홈</Link>
        <h1>대응안: 무엇부터 할까요?</h1>
      </div>
      <div className="agent-grid">
        <div>
          <div className="chat" aria-live="polite">
            {msgs.map((m, i) => (
              <div key={i} className={`msg ${m.who}`}>
                {m.text}
              </div>
            ))}
          </div>
          <div className="chips">{CHIPS.map((c) => <button key={c} onClick={() => send(c)}>{c}</button>)}</div>
          <form onSubmit={(e) => { e.preventDefault(); send(text) }} style={{ display: 'flex', gap: 8 }}>
            <input type="text" aria-label="질문 입력" placeholder="질문을 입력하세요" value={text} onChange={(e) => setText(e.target.value)} />
            <button className="btn" type="submit" style={{ whiteSpace: 'nowrap' }}>보내기</button>
          </form>
        </div>

        <div>
          <p className="muted" style={{ marginBottom: 10 }}>
            {isRisk ? '현재 상황' : '가정한 상황'}: 최저 잔액 <b className="num">{won(crisis.minP50)}</b> · 효과 큰 순서
          </p>
          {ranked.map((p, i) => (
            <article className={`plan ${i === 0 ? 'top' : ''}`} key={p.id}>
              <header>
                <h3>{p.title}</h3>
                <span className={`pill ${p.solved ? '' : 'yellow'}`}>{p.solved ? '부족 해소' : '부분 개선'}</span>
              </header>
              <p className="muted" style={{ fontSize: 13.5 }}>{p.how}</p>
              <p className="gain num">최저 잔액 {won(crisis.minP50)} → <b>{won(p.f.minP50)}</b> ({p.gain >= 0 ? '+' : ''}{won(p.gain)})</p>
              <p className="cost">{p.cost}</p>
            </article>
          ))}
        </div>
      </div>
    </>
  )
}
