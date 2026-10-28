// 범례: 노드 타입은 색과 모양을 함께, 엣지는 실선·점선·위험 경로로 설명한다.
const NODE_ITEMS: { label: string; color: string; fill: string; dash?: string; shape: React.ReactNode }[] = [
  { label: '금액', color: 'var(--muted)', fill: 'var(--widget)', shape: <polygon points="5,1 11,1 15,5 15,11 11,15 5,15 1,11 1,5" /> },
  { label: '거래처', color: 'var(--brand)', fill: 'var(--brand-bg)', shape: <ellipse cx="8" cy="8" rx="7" ry="5" /> },
  { label: '카드', color: 'var(--green)', fill: 'var(--green-bg)', shape: <polygon points="1,3 11,3 15,8 11,13 1,13" /> },
  { label: '대출', color: 'var(--yellow)', fill: 'var(--yellow-bg)', shape: <polygon points="4,2 12,2 15,8 12,14 4,14 1,8" /> },
  { label: '계약서', color: 'var(--muted)', fill: 'var(--surface)', dash: '3 2', shape: <rect x="1.5" y="3" width="13" height="10" rx="2" /> },
  { label: '조항', color: '#8a63d2', fill: 'var(--surface)', shape: <polygon points="8,1 15,8 8,15 1,8" /> },
  { label: '신호', color: '#3b82c4', fill: 'var(--surface)', shape: <polygon points="8,1 10,6 15,6 11,9.5 12.5,15 8,11.5 3.5,15 5,9.5 1,6 6,6" /> },
]

export default function Legend() {
  return (
    <div className="legend-row" aria-label="범례">
      {NODE_ITEMS.map((it) => (
        <span className="k" key={it.label}>
          <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden style={{ fill: it.fill, stroke: it.color, strokeWidth: 1.6, strokeDasharray: it.dash }}>{it.shape}</svg>
          {it.label}
        </span>
      ))}
      <span className="sep" aria-hidden />
      <span className="k"><svg width="22" height="8" aria-hidden><line x1="0" y1="4" x2="22" y2="4" stroke="var(--muted)" strokeWidth="2.5" /></svg>돈이 움직임</span>
      <span className="k"><svg width="22" height="8" aria-hidden><line x1="0" y1="4" x2="22" y2="4" stroke="var(--muted)" strokeWidth="2" strokeDasharray="1.5 3" strokeLinecap="round" /></svg>조건·규칙</span>
      <span className="k"><svg width="22" height="8" aria-hidden><line x1="0" y1="4" x2="22" y2="4" stroke="#3b82c4" strokeWidth="1" strokeDasharray="1.5 3" strokeLinecap="round" /></svg>신호</span>
      <span className="k"><svg width="22" height="8" aria-hidden><line x1="0" y1="4" x2="22" y2="4" stroke="var(--red)" strokeWidth="3" /></svg>위험 경로</span>
    </div>
  )
}
