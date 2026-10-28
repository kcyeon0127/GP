import { Link } from 'react-router-dom'
import { alertWindowEvents, baseEvents, business, dayLabel, knownDelays, won } from '../data.ts'
import { base, signalOf } from '../engine.ts'

// 자금 상태가 위험·주의일 때 홈 하단에 나오는 설명: 왜 부족해지는지를 예측 엔진과 데이터로 계산해서 풀어 준다.
export default function WhyRisk() {
  const f = base.forecast
  const sig = signalOf(f)
  // 빨강은 0원, 노랑은 안전 잔액을 기준으로 처음 밑도는 날을 찾는다
  const floor = sig.level === 'red' ? business.minBalance : business.safeBalance
  const shortDay = f.firstShortDay ?? f.p50.findIndex((v, d) => d >= 1 && v < floor)
  if (sig.level === 'green' || shortDay <= 0) return null

  const level = sig.level === 'red' ? '위험' : '주의'
  const outs = alertWindowEvents.filter((e) => e.direction === 'out' && e.day <= shortDay).sort((a, b) => a.day - b.day)
  const outTotal = outs.reduce((a, e) => a + e.amount, 0)
  const ending = f.p50[shortDay]
  const available = ending + outTotal // 그날까지 쓸 수 있는 돈(예상) = 그날 잔액 + 그날까지 나간 돈
  const need = Math.max(0, floor - f.minP50) // 끝까지 버티려면 더 필요한 돈
  const delayed = Object.entries(knownDelays).flatMap(([id, d]) => {
    const e = baseEvents.find((x) => x.id === id)
    return e ? [{ e, d, from: e.day - d }] : []
  })
  const recovery = f.p50.findIndex((v, d) => d > shortDay && v >= floor)
  const max = Math.max(outTotal, available, 1)

  return (
    <section className="why card" aria-labelledby="why-h">
      <h2 id="why-h">왜 자금 상태가 “{level}”일까요?</h2>
      <p className="sub">{dayLabel(shortDay)}에 잔액이 <b className="num">{won(ending)}</b>까지 내려가요.</p>

      <ol className="why-list">
        <li>
          <b>들어올 돈이 늦어졌어요.</b>{' '}
          {delayed.length
            ? delayed.map((x) => `${x.e.label.replace(' 정산', '')} 정산 ${won(x.e.amount)}이 ${dayLabel(x.from)}→${dayLabel(x.e.day)}, ${x.d}일 밀렸어요.`).join(' ')
            : `${dayLabel(shortDay)}까지 들어오는 큰 정산이 많지 않아요.`}
        </li>
        <li>
          <b>나갈 돈이 먼저 몰려요.</b>{' '}
          {dayLabel(shortDay)}까지 {outs.map((e) => `${e.label.replace(' 매입 대금', '')} ${won(e.amount)}`).join('·')} (합계 {won(outTotal)}).
        </li>
        <li>
          <b>쓸 수 있는 돈이 모자라요.</b> 오늘 잔액 {won(business.startBalance)}에 예상 입금을 더해도 {won(available)}, {won(Math.max(0, outTotal - available))} 부족해요.
        </li>
      </ol>

      <div className="why-bars" role="img" aria-label={`${dayLabel(shortDay)}까지 쓸 수 있는 돈 ${won(available)}, 나갈 돈 ${won(outTotal)}`}>
        <div className="why-bar"><span>쓸 수 있는 돈</span><i className="ok" style={{ width: `${(available / max) * 100}%` }} /><b className="num">{won(available)}</b></div>
        <div className="why-bar"><span>나갈 돈</span><i className="bad" style={{ width: `${(outTotal / max) * 100}%` }} /><b className="num">{won(outTotal)}</b></div>
      </div>

      <p className="why-foot">
        {recovery > 0 ? `${dayLabel(recovery)}쯤 ${delayed[0]?.e.label.replace(' 정산', '') ?? ''} 입금으로 풀리지만, ` : ''}
        그때까지 <b className="num">{won(need)}</b>이 더 필요해요.
      </p>
      <p className="why-links"><Link to="/agent">대응안 보기 →</Link><Link to="/map">번지는 길 보기 →</Link></p>
    </section>
  )
}
