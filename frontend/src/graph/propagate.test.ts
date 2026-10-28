// 전파 엔진 단위 테스트. 실행: npm test  (Node 내장 test runner, 추가 라이브러리 없음)
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { graph } from '../data/financeGraph.ts'
import { HANDLERS, propagate } from './propagate.ts'

const status = (r: ReturnType<typeof propagate>, id: string) => r.nodes.get(id)?.status
const hasPath = (r: ReturnType<typeof propagate>, ids: string[]) => r.paths.some((p) => ids.every((id) => p.includes(id)) && ids.every((id, i) => i === 0 || p.indexOf(id) > p.indexOf(ids[i - 1])))

test('모든 엣지 타입에 handler가 있다', () => {
  const types = new Set(graph.edges.map((e) => e.type))
  for (const t of types) assert.equal(typeof HANDLERS[t], 'function', t)
  assert.equal(Object.keys(HANDLERS).length, 12)
})

test('한빛식자재 14일 지연 → 정산 → 사업용 계좌 → 운영자금대출 상환이 at_risk', () => {
  const r = propagate(graph, { type: 'settlement_delay', partnerId: 'P1', days: 14 })
  assert.equal(status(r, 'S1'), 'at_risk')
  assert.equal(status(r, 'ACC'), 'at_risk')
  assert.equal(status(r, 'L1'), 'at_risk')
  assert.ok(hasPath(r, ['P1', 'S1', 'ACC', 'L1']), '경로 P1→S1→ACC→L1')
  assert.ok(r.patches.some((p) => p.kind === 'shift' && 'id' in p && p.id === 'S1' && p.days === 14))
  assert.ok(r.balance.minP50 < r.balance.baseMinP50)
  assert.ok(r.balance.repayments.some((x) => x.id === 'L1'))
  // 연체가 아니라 위험이므로 조항은 발동(triggered)이 아니라 at_risk
  assert.notEqual(status(r, 'CL_L1a'), 'triggered')
  // 신호가 이 시나리오를 제안한다
  assert.ok(r.suggestions.some((x) => x.signalId === 'SG1'))
})

test('운영자금대출 연체 → 약정 → 기한이익상실 → 교차 조항 → 시설자금 약정 → 시설자금대출 (3홉 이상)', () => {
  const r = propagate(graph, { type: 'loan_default', loanId: 'L1' })
  for (const id of ['K_L1', 'CL_L1a', 'CL_L1b', 'K_L2', 'L2']) assert.equal(status(r, id), 'triggered', id)
  assert.ok(hasPath(r, ['L1', 'K_L1', 'CL_L1b', 'K_L2', 'L2']))
  assert.ok(r.hops >= 3)
  assert.ok(r.edges.size >= 4)
  assert.notEqual(status(r, 'CL_L1c'), 'triggered') // 중도상환수수료는 연체와 무관
})

test('대성유통 매입 대금을 A카드로 변경 → 출금일이 결제일로 이동, 2% 할인, 최저 잔액 개선', () => {
  const r = propagate(graph, { type: 'payment_switch', targetId: 'Y1', cardId: 'C1' })
  const move = r.patches.find((p) => p.kind === 'setDay' && p.id === 'Y1')
  assert.ok(move && move.kind === 'setDay' && move.day === 24, 'A카드 결제일 25일 = 오늘+24일')
  const disc = r.patches.find((p) => p.kind === 'amount' && p.id === 'Y1')
  assert.ok(disc && disc.kind === 'amount' && Math.abs((disc.factor ?? 1) - 0.98) < 1e-9)
  assert.ok(r.balance.minP50 > r.balance.baseMinP50)
  assert.equal(status(r, 'Y1'), 'improved')
  assert.match(r.nodes.get('Y1')!.reason, /2% 청구할인 적용/)
})

test('전월 실적 조건을 충족하지 못하면 할인 미적용으로 표시', () => {
  const r = propagate(graph, { type: 'payment_switch', targetId: 'Y1', cardId: 'C1', prevMonthSpend: 1_000_000 })
  assert.ok(!r.patches.some((p) => p.kind === 'amount' && p.id === 'Y1'), '할인 패치 없음')
  assert.match(r.nodes.get('Y1')!.reason, /미적용/)
})

test('대성유통 대금 30일 지연 → 공급 중단 조항 triggered, 20일이면 at_risk', () => {
  const r30 = propagate(graph, { type: 'settlement_delay', partnerId: 'P4', days: 30 })
  assert.equal(status(r30, 'CL_SUP2'), 'triggered')
  assert.equal(status(r30, 'K_SUP'), 'at_risk')
  const r20 = propagate(graph, { type: 'settlement_delay', partnerId: 'P4', days: 20 })
  assert.equal(status(r20, 'CL_SUP2'), 'at_risk')
})

test('금리 +1%p → 변동금리인 운영자금대출만 상환액 증가, 시설자금대출은 변화 없음', () => {
  const r = propagate(graph, { type: 'rate_up', pp: 1 })
  assert.ok(r.nodes.has('L1'))
  assert.ok(!r.nodes.has('L2'))
  const p = r.patches.find((x) => x.kind === 'amount' && x.id === 'L1')
  assert.ok(p && p.kind === 'amount' && p.delta === Math.round((62_000_000 * 0.01) / 12))
  assert.ok(!r.patches.some((x) => 'id' in x && x.id === 'L2'))
})

test('매출 20% 하락 → 모든 정산액·현장 매출 감소 → 계좌 위험 → 상환 위험', () => {
  const r = propagate(graph, { type: 'revenue_drop', pct: 20 })
  assert.equal(status(r, 'ACC'), 'at_risk')
  for (const id of ['S1', 'S2', 'S3']) assert.equal(status(r, id), 'changed', id)
  const s1 = r.patches.find((p) => p.kind === 'amount' && p.id === 'S1')
  assert.ok(s1 && s1.kind === 'amount' && Math.abs((s1.factor ?? 1) - 0.8) < 1e-9)
  const sales = r.patches.find((p) => p.kind === 'sales')
  assert.ok(sales && sales.kind === 'sales' && Math.abs(sales.factor - 0.8) < 1e-9)
  assert.ok(r.balance.minP50 < r.balance.baseMinP50)
  assert.ok(r.balance.repayments.some((x) => x.id === 'L1'), '운영자금대출 상환이 위험해진다')
  // 하락 폭이 클수록 최저 잔액이 더 낮다
  const r40 = propagate(graph, { type: 'revenue_drop', pct: 40 })
  assert.ok(r40.balance.minP50 < r.balance.minP50)
})

test('거래처 폐업 → 정산 미회수 → 계좌 위험', () => {
  const r = propagate(graph, { type: 'partner_closure', partnerId: 'P1' })
  assert.equal(status(r, 'S1'), 'triggered')
  assert.equal(status(r, 'ACC'), 'at_risk')
  assert.ok(r.balance.minP50 < r.balance.baseMinP50)
})

test('propagate는 입력 그래프를 바꾸지 않고, 같은 입력이면 같은 결과를 낸다', () => {
  const before = JSON.stringify(graph)
  const a = propagate(graph, { type: 'payment_switch', targetId: 'Y1', cardId: 'C1' })
  const b = propagate(graph, { type: 'payment_switch', targetId: 'Y1', cardId: 'C1' })
  assert.equal(JSON.stringify(graph), before)
  assert.deepEqual([...a.nodes.keys()].sort(), [...b.nodes.keys()].sort())
  assert.equal(a.balance.minP50, b.balance.minP50)
})

test('전파는 최대 5홉', () => {
  for (const shock of [
    { type: 'settlement_delay', partnerId: 'P1', days: 14 }, { type: 'loan_default', loanId: 'L1' }, { type: 'loan_default', loanId: 'L2' },
  ] as const) assert.ok(propagate(graph, shock).hops <= 5)
})
