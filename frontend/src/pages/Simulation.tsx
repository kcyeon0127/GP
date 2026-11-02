import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import AskBot from '../components/AskBot.tsx'
import BalanceChart from '../components/BalanceChart.tsx'
import Signal from '../components/Signal.tsx'
import { applyShocks, base, compare, forecast, signalOf, type Shock } from '../engine.ts'
import { dayLabel, partners, won } from '../data.ts'
import { isRisk } from '../demo.ts'

type Kind = 'settlement_delay' | 'revenue_drop' | 'rate_up' | 'partner_closure'
const KINDS: { id: Kind; label: string }[] = [
  { id: 'settlement_delay', label: '정산 지연' },
  { id: 'revenue_drop', label: '매출 하락' },
  { id: 'rate_up', label: '금리 인상' },
  { id: 'partner_closure', label: '거래처 폐업' },
]
const sales = partners.filter((p) => p.role === 'sales')

// What-if 홈: 충격 조건을 직접 조절하는 화면. 오른쪽 아래 챗봇에 말로 물으면 /simulation/ask 로 이어진다.
export default function Simulation() {
  const [kind, setKind] = useState<Kind>(isRisk ? 'revenue_drop' : 'settlement_delay')
  const [partnerId, setPartnerId] = useState('P1')
  const [days, setDays] = useState(14)
  const [pct, setPct] = useState(20)
  const [bp, setBp] = useState(200)

  const shock: Shock =
    kind === 'settlement_delay' ? { type: kind, partnerId, days }
    : kind === 'revenue_drop' ? { type: kind, pct }
    : kind === 'rate_up' ? { type: kind, bp }
    : { type: kind, partnerId }

  const result = useMemo(() => {
    const st = applyShocks([shock])
    const f = forecast(st)
    return { f, diff: compare(base.forecast, f, st.events), sig: signalOf(f) }
  }, [shock.type, partnerId, days, pct, bp]) // eslint-disable-line react-hooks/exhaustive-deps

  const { f, diff, sig } = result
  const delta = diff.minP50Delta

  return (
    <>
      <div className="page-head">
        <Link to="/" className="back">← 홈</Link>
        <h1>시나리오: 이러면 어떻게 될까요?</h1>
      </div>
      <div className="hub-grid">
        <div className="stack">
          <Signal {...sig} />
          <div className="card">
            <div className="kpis">
              <div className="kpi"><span>예상 최저 잔액</span><b className={`num ${f.minP50 < 0 ? 'bad' : ''}`}>{won(f.minP50)}</b></div>
              <div className="kpi"><span>기준선 대비</span><b className={`num ${delta < 0 ? 'bad' : 'good'}`}>{delta >= 0 ? '+' : ''}{won(delta)}</b></div>
              <div className="kpi"><span>첫 부족 예상일</span><b className="num">{diff.firstShortAfter ? dayLabel(diff.firstShortAfter) : '없음'}</b></div>
            </div>
            <BalanceChart base={base.forecast} scenario={f} />
            <div className="legend">
              <span><i style={{ background: 'var(--band)' }} />기준선</span>
              <span><i style={{ background: 'var(--red)' }} />시나리오</span>
              <span>점선: 잔액 0원</span>
            </div>
          </div>
          <div className="card">
            <h2>새로 위험해진 지급</h2>
            {diff.newlyRisky.length === 0 ? (
              <p className="sub" style={{ marginBottom: 0 }}>기준선보다 위험이 10%p 이상 늘어난 지급이 없습니다.</p>
            ) : (
              <>
                <p className="sub">지급 당일 잔액이 부족할 확률이 늘어난 항목입니다.</p>
                {diff.newlyRisky.map((r) => (
                  <div className="row" key={r.id}>
                    <span>{r.label}</span>
                    <span className="num">{Math.round(r.before * 100)}% → <b style={{ color: 'var(--red)' }}>{Math.round(r.after * 100)}%</b></span>
                  </div>
                ))}
                <p style={{ marginTop: 14 }}><Link className="btn" to="/agent" style={{ textDecoration: 'none', display: 'inline-block' }}>대응안 보기</Link></p>
              </>
            )}
          </div>
        </div>

        <div className="stack">
          <div className="card">
            <h2>충격 조건</h2>
            <p className="sub">조건을 바꾸면 기준선과 즉시 비교됩니다.</p>
            <div className="field">
              <label id="k">충격 종류</label>
              <div className="seg" role="group" aria-labelledby="k">
                {KINDS.map((k) => (
                  <button key={k.id} className={kind === k.id ? 'on' : ''} aria-pressed={kind === k.id} onClick={() => setKind(k.id)}>{k.label}</button>
                ))}
              </div>
            </div>
            {(kind === 'settlement_delay' || kind === 'partner_closure') && (
              <div className="field">
                <label htmlFor="p">대상 거래처</label>
                <select id="p" value={partnerId} onChange={(e) => setPartnerId(e.target.value)}>
                  {sales.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                </select>
              </div>
            )}
            {kind === 'settlement_delay' && (
              <div className="field">
                <label htmlFor="d">지연 일수: {days}일</label>
                <input id="d" type="range" min={1} max={28} value={days} onChange={(e) => setDays(+e.target.value)} />
              </div>
            )}
            {kind === 'revenue_drop' && (
              <div className="field">
                <label htmlFor="r">매출 감소율: {pct}%</label>
                <input id="r" type="range" min={5} max={60} step={5} value={pct} onChange={(e) => setPct(+e.target.value)} />
              </div>
            )}
            {kind === 'rate_up' && (
              <div className="field">
                <label htmlFor="b">금리 상승폭: +{(bp / 100).toFixed(1)}%p</label>
                <input id="b" type="range" min={50} max={500} step={50} value={bp} onChange={(e) => setBp(+e.target.value)} />
                <span className="muted" style={{ fontSize: 13 }}>변동금리 대출에만 적용됩니다.</span>
              </div>
            )}
          </div>
          <AskBot />
        </div>
      </div>
    </>
  )
}
