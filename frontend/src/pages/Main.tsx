import { useState } from 'react'
import { Link } from 'react-router-dom'
import BalanceChart from '../components/BalanceChart.tsx'
import MiniMap from '../components/MiniMap.tsx'
import Signal from '../components/Signal.tsx'
import WhyRisk from '../components/WhyRisk.tsx'
import { DriversCard, LiveSignal } from '../components/live/AlertParts.tsx'
import LiveChart from '../components/live/LiveChart.tsx'
import LiveWhy from '../components/live/LiveWhy.tsx'
import { useLiveData } from '../live.ts'
import { md, useApiStatus } from '../api.ts'
import { HORIZON, WINDOW, base, signalOf } from '../engine.ts'
import { alertWindowEvents, dayLabel, news, pastBalances, won } from '../data.ts'

const sig = signalOf(base.forecast)
const upcoming = alertWindowEvents.filter((e) => e.direction === 'out').sort((a, b) => a.day - b.day)
const incoming = alertWindowEvents.filter((e) => e.kind === 'settlement').sort((a, b) => a.day - b.day)

export default function Main() {
  const live = useApiStatus()
  if (live) return <LiveHome />
  return <DemoHome checking={live === null} />
}

function LiveHome() {
  const { data, err, reload } = useLiveData()
  const [full, setFull] = useState(false)
  const [open, setOpen] = useState(false)
  const [balance, setBalance] = useState('')
  if (err) return <div className="card" role="alert">서버 계산을 불러오지 못했습니다: {err}</div>
  if (!data) return <div className="page-head"><h1>오늘의 자금 현황</h1></div>
  const { f, events, stats } = data
  const windowEnd = f.daily?.[27]?.date ?? ''
  const soon = events.filter((e) => e.date <= windowEnd)
  const upcomingLive = soon.filter((e) => e.dir === 'OUT')
  const incomingLive = soon.filter((e) => e.dir === 'IN')
  const laterShort = f.first_shortage_date && f.first_shortage_date > windowEnd ? f.first_shortage_date : null
  const trigger = f.signal === 'RED' ? f.first_shortage_date : f.first_below_safe_date
  const tile = (to: string, title: string, body: string, go: string) => (
    <Link to={to} className="tile"><h3>{title}</h3><p>{body}</p><div className="go">{go}</div></Link>
  )
  return (
    <>
      <div className="page-head"><h1>오늘의 자금 현황</h1></div>
      <div className="main-grid">
        <div className="stack">
          <LiveSignal f={f} open={open} onToggle={() => setOpen((v) => !v)} />
          {open && <DriversCard runId={f.run_id} trigger={trigger} />}
          <div className="split">
            <MiniMap stats={stats} />
            <div className="card">
              <h2>향후 {full ? '12주' : '4주'} 예상 잔액 {laterShort && <span className="pill red">{md(laterShort)} 부족 예상</span>}</h2>
              <p className="sub">
                {f.first_shortage_date
                  ? <>최초 부족일 <b className="num bad">{md(f.first_shortage_date)}</b> · 부족액 <b className="num bad">{won(f.shortage_amount!)}</b>. </>
                  : <><b>부족 예상 없음</b>. </>}
                최저 잔액은 <b className="num">{won(f.min_balance)}</b> ({md(f.min_balance_date)})예요. 0원 아래는 빨간색, 노란 점선은 안전 잔액이에요.
              </p>
              {!f.has_events && <p className="empty-note">{f.message} <Link to="/ledger">일정 등록하기 →</Link></p>}
              <LiveChart f={f} days={full ? 84 : 28} height={230} />
              <p className="later">
                기준일 {md(f.base_date)} · 현재 잔액 {won(f.start_balance)}
                <button type="button" className="link-btn" aria-pressed={full} onClick={() => setFull((v) => !v)}>{full ? '4주만 보기' : '12주 전체 보기'}</button>
              </p>
              <form className="rerun" onSubmit={(e) => { e.preventDefault(); if (balance) { reload({ current_balance: +balance }); setBalance('') } }}>
                <label htmlFor="bal">현재 잔액</label>
                <input id="bal" type="number" inputMode="numeric" placeholder={String(f.start_balance)} value={balance} onChange={(e) => setBalance(e.target.value)} />
                <button className="btn ghost" type="submit">다시 계산</button>
              </form>
            </div>
          </div>
          {f.signal === 'GREEN' ? (
            <div className="tiles">
              {tile('/simulation', '이러면 어떻게 될까?', '거래처 정산이 늦어지거나 매출이 줄면 잔액이 어떻게 변하는지 미리 확인합니다.', '시나리오 해 보기 →')}
              {tile('/map', '왜 모자랄까?', '돈이 어디서 들어와 어디로 나가는지 관계망으로 보고 위험 경로를 확인합니다.', '원인 보기 →')}
              {tile('/agent', '무엇부터 할까?', '부족이 예상될 때 효과가 계산된 대응안을 순위로 받아봅니다.', '대응안 보기 →')}
            </div>
          ) : (
            <div className="tiles risk">
              {tile('/simulation', '이러면 어떻게 될까?', '매출이 줄거나 금리가 오르면 더 나빠지는지, 대출을 받으면 나아지는지 미리 확인합니다.', '시나리오 해 보기 →')}
              {tile('/agent', '무엇부터 할까?', '효과가 계산된 대응안을 순위로 받아봅니다.', '대응안 보기 →')}
              <LiveWhy f={f} />
            </div>
          )}
        </div>

        <aside className="widgets" aria-label="위젯">
          <section className="wsec" aria-labelledby="w-out">
            <h3 id="w-out">다가오는 지급 <span className="count">{upcomingLive.length}</span></h3>
            <div className="wscroll" tabIndex={0} role="region" aria-label="다가오는 지급 목록">
              {upcomingLive.map((e) => <div className="row" key={e.key}><span>{e.label}<br /><span className="muted">{md(e.date)}</span></span><b className="num">{won(e.amount)}</b></div>)}
            </div>
          </section>
          <section className="wsec" aria-labelledby="w-in">
            <h3 id="w-in">받을 정산 <span className="count">{incomingLive.length}</span></h3>
            <div className="wscroll" tabIndex={0} role="region" aria-label="받을 정산 목록">
              {incomingLive.map((e) => <div className="row" key={e.key}><span>{e.label.replace(' 정산', '')}<br /><span className="muted">{md(e.date)} 예정</span></span><b className="num">{won(e.amount)}</b></div>)}
            </div>
          </section>
          <section className="wsec" aria-labelledby="w-news">
            <h3 id="w-news">금융 뉴스 <span className="count">{news.length}</span> <span className="pill soon">샘플</span></h3>
            <div className="wscroll" tabIndex={0} role="region" aria-label="금융 뉴스 목록">
              {news.map((n) => <div className="row news" key={n.id}><span><span className="pill">{n.tag}</span> {n.title}<br /><span className="muted">{n.source} · {n.date}</span></span></div>)}
            </div>
          </section>
        </aside>
      </div>
      <p className="ask-entry"><Link to="/agent">✦ 대응 에이전트에게 물어보기</Link> <span className="pill soon">확장 예정</span></p>
    </>
  )
}

function DemoHome({ checking }: { checking: boolean }) {
  const f = base.forecast
  const [full, setFull] = useState(false)
  const later = f.later
  const laterWeek = later.firstShortDay ? Math.ceil(later.firstShortDay / 7) : null
  return (
    <>
      <div className="page-head"><h1>오늘의 자금 현황</h1></div>
      {!checking && <p className="banner">서버에 연결되지 않아 합성 데이터 시연 화면을 보여 드려요.</p>}
      <div className="main-grid">
        <div className="stack">
          <Signal {...sig} />
          <div className="split">
            <MiniMap />
            <div className="card">
              <h2>잔액 추이와 {full ? '향후 12주' : '향후 4주'} 예측 {laterWeek && <span className="pill red">{laterWeek}주 뒤 부족 예상</span>}</h2>
              <p className="sub">
                4주 안 최저 잔액은 <b className="num">{won(f.minP50)}</b> ({dayLabel(f.minDay)} 전후)로 예상해요. 실선은 최근 7일, 점선은 예측, 음영은 상황이 나쁠 때부터 좋을 때까지의 예상 범위예요.
              </p>
              <BalanceChart base={f} history={pastBalances} width={440} height={250} days={full ? HORIZON : WINDOW} />
              <p className="later">
                5~12주: 최저 잔액 <b className="num">{won(later.minP50)}</b> ({dayLabel(later.minDay)} 전후),{' '}
                {later.firstShortDay ? <b className="bad">{dayLabel(later.firstShortDay)}부터 부족 예상</b> : '부족 예상 없음'}
                <button type="button" className="link-btn" aria-pressed={full} onClick={() => setFull((v) => !v)}>{full ? '4주만 보기' : '12주 전체 보기'}</button>
              </p>
            </div>
          </div>
          {sig.level === 'green' ? (
            <div className="tiles">
              <Link to="/simulation" className="tile">
                <h3>이러면 어떻게 될까?</h3>
                <p>거래처 정산이 늦어지거나 매출이 줄면 잔액이 어떻게 변하는지 미리 확인합니다.</p>
                <div className="go">시나리오 해 보기 →</div>
              </Link>
              <Link to="/map" className="tile">
                <h3>왜 모자랄까?</h3>
                <p>돈이 어디서 들어와 어디로 나가는지 관계망으로 보고 위험 경로를 확인합니다.</p>
                <div className="go">원인 보기 →</div>
              </Link>
              <Link to="/agent" className="tile">
                <h3>무엇부터 할까?</h3>
                <p>부족이 예상될 때 효과가 계산된 대응안을 순위로 받아봅니다.</p>
                <div className="go">대응안 보기 →</div>
              </Link>
            </div>
          ) : (
            <div className="tiles risk">
              <Link to="/simulation" className="tile">
                <h3>이러면 어떻게 될까?</h3>
                <p>매출이 줄거나 금리가 오르면 더 나빠지는지, 대출을 받으면 나아지는지 미리 확인합니다.</p>
                <div className="go">시나리오 해 보기 →</div>
              </Link>
              <Link to="/agent" className="tile">
                <h3>무엇부터 할까?</h3>
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
            <h3 id="w-news">금융 뉴스 <span className="count">{news.length}</span> <span className="pill soon">샘플</span></h3>
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
      <p className="ask-entry"><Link to="/agent">✦ 대응 에이전트에게 물어보기</Link> <span className="pill soon">확장 예정</span></p>
    </>
  )
}
