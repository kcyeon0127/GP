import type { Signal as Level } from '../engine.ts'

const TITLE: Record<Level, string> = { green: '안정', yellow: '주의', red: '위험' }

export default function Signal({ level, reason }: { level: Level; reason: string }) {
  return (
    <div className={`signal ${level}`} role="status">
      <span className="lamp" aria-hidden />
      <div>
        <strong>자금 상태: {TITLE[level]}</strong>
        <p>{reason}</p>
      </div>
    </div>
  )
}
