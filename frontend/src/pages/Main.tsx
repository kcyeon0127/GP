import { Link } from 'react-router-dom'
import BalanceChart from '../components/BalanceChart.tsx'
import MiniMap from '../components/MiniMap.tsx'
import Signal from '../components/Signal.tsx'
import WhyRisk from '../components/WhyRisk.tsx'
import { base, signalOf } from '../engine.ts'
import { baseEvents, dayLabel, news, pastBalances, won } from '../data.ts'

const sig = signalOf(base.forecast)
const upcoming = baseEvents.filter((e) => e.direction === 'out').sort((a, b) => a.day - b.day)
const incoming = baseEvents.filter((e) => e.kind === 'settlement').sort((a, b) => a.day - b.day)

export default function Main() {
  const f = base.forecast
  return (
    <>
      <div className="page-head"><h1>오늘의 자금 현황</h1></div>
      <div className="main-grid">
        <div className="stack">
          <Signal {...sig} />
          <div className="split">
            <MiniMap />
            <div className="card">
              <h2>잔액 추이와 향후 28일 예측</h2>
              <p className="sub">
                최저 잔액은 <b className="num">{won(f.minP50)}</b> ({dayLabel(f.minDay)} 전후)로 예상해요. 실선은 최근 7일, 점선은 예측, 음영은 상황이 나쁠 때부터 좋을 때까지의 예상 범위예요.
              </p>
              <BalanceChart base={f} history={pastBalances} width={440} height={250} />
            </div>
          </div>
          {sig.level === 'green' ? (
            <div className="tiles">
              <Link to="/simulation" className="tile">
                <h3>What-if 시뮬레이션</h3>
                <p>거래처 정산이 늦어지거나 매출이 줄면 잔액이 어떻게 변하는지 미리 확인합니다.</p>
                <div className="go">시뮬레이션 열기 →</div>
              </Link>
              <Link to="/map" className="tile">
                <h3>금융지도</h3>
                <p>돈이 어디서 들어와 어디로 나가는지 관계망으로 보고 위험 경로를 확인합니다.</p>
                <div className="go">지도 열기 →</div>
              </Link>
              <Link to="/agent" className="tile">
                <h3>대응 에이전트</h3>
                <p>부족이 예상될 때 효과가 계산된 대응안을 순위로 받아봅니다.</p>
                <div className="go">대응안 보기 →</div>
              </Link>
            </div>
          ) : (
            <div className="tiles risk">
              <Link to="/simulation" className="tile">
                <h3>What-if 시뮬레이션</h3>
                <p>매출이 줄거나 금리가 오르면 더 나빠지는지, 대출을 받으면 나아지는지 미리 확인합니다.</p>
                <div className="go">시뮬레이션 열기 →</div>
              </Link>
              <Link to="/agent" className="tile">
                <h3>대응 에이전트</h3>
                <p>효과가 계산된 대응안을 순위로 받아봅니다.</p>
                <div className="go">대응안 보기 →</div>
              </Link>
              <WhyRisk />
            </div>
          )}
        </div>

        <aside className="widgets" aria-label="위젯">
          <section className="wsec" aria-labelledby="w-out">
            <h3 id="w-out">다가오는 지급 <span className="count">{upcoming.length}</span></h3>
            <div className="wscroll" tabIndex={0} role="region" aria-label="다가오는 지급 목록">
              {upcoming.map((e) => (
                <div className="row" key={e.id}><span>{e.label}<br /><span className="muted">{dayLabel(e.day)}</span></span><b className="num">{won(e.amount)}</b></div>
              ))}
            </div>
          </section>
          <section className="wsec" aria-labelledby="w-in">
            <h3 id="w-in">받을 정산 <span className="count">{incoming.length}</span></h3>
            <div className="wscroll" tabIndex={0} role="region" aria-label="받을 정산 목록">
              {incoming.map((e) => (
                <div className="row" key={e.id}>
                  <span>{e.label.replace(' 정산', '')}<br /><span className="muted">{dayLabel(e.day)} 예정</span></span>
                  <b className="num">{won(e.amount)}</b>
                </div>
              ))}
            </div>
          </section>
          <section className="wsec" aria-labelledby="w-news">
            <h3 id="w-news">금융 뉴스 <span className="count">{news.length}</span></h3>
            <div className="wscroll" tabIndex={0} role="region" aria-label="금융 뉴스 목록">
              {news.map((n) => (
                <div className="row news" key={n.id}>
                  <span><span className="pill">{n.tag}</span> {n.title}<br /><span className="muted">{n.source} · {n.date}</span></span>
                </div>
              ))}
            </div>
          </section>
        </aside>
      </div>
      <Link to="/agent" className="ai-entry">✦ 대응 에이전트에게 물어보기</Link>
    </>
  )
}
