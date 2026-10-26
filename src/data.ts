// 합성 데이터: 식자재 납품업 페르소나 1종 (설계 문서 §합성 데이터). 실데이터 연동 시 이 파일만 교체한다.
// 위험 상황 데모(VITE_DEMO=risk)는 같은 사업장에서 한빛식자재 정산 지연이 확정되고 잔액이 줄어든 상태다.
import { isRisk } from './demo.ts'

// 이미 확정된 정산 지연(일). 금융지도의 "현재 상황" 표시에 쓴다.
export const knownDelays: Record<string, number> = isRisk ? { S1: 14 } : {}

export type EventKind = 'settlement' | 'payable' | 'loan' | 'fixed'

export interface CashEvent {
  id: string
  label: string
  kind: EventKind
  day: number // 오늘 기준 +N일 (1~28)
  amount: number // 원, 항상 양수
  direction: 'in' | 'out'
  partnerId?: string
  loanId?: string
  delay?: { mean: number; sd: number } // 정산 지연 분포(일)
  floatingRate?: boolean
}

export interface Partner {
  id: string
  name: string
  role: 'sales' | 'purchase'
  taxStatus: '계속사업자' | '휴업' | '폐업'
}

export interface Business {
  name: string
  industry: string
  region: string
  openedAt: string
  startBalance: number
  minBalance: number
  salesPerDay: number
  loanBalances: Record<string, number>
}

export const business: Business = {
  name: '한결 식자재 납품',
  industry: '식자재 도소매 (C-47)',
  region: '서울 마포구',
  openedAt: '2021-03-15',
  startBalance: isRisk ? 2_900_000 : 3_200_000,
  minBalance: 0,
  salesPerDay: 230_000,
  loanBalances: { L1: 62_000_000, L2: 18_000_000 },
}

export const partners: Partner[] = [
  { id: 'P1', name: '한빛식자재', role: 'sales', taxStatus: '계속사업자' },
  { id: 'P2', name: '청춘마켓', role: 'sales', taxStatus: '계속사업자' },
  { id: 'P3', name: '온누리푸드', role: 'sales', taxStatus: '계속사업자' },
  { id: 'P4', name: '대성유통', role: 'purchase', taxStatus: '계속사업자' },
]

export const baseEvents: CashEvent[] = [
  { id: 'S1', label: '한빛식자재 정산', kind: 'settlement', day: 6 + (knownDelays.S1 ?? 0), amount: 3_200_000, direction: 'in', partnerId: 'P1', delay: { mean: 2, sd: 2 } },
  { id: 'S2', label: '청춘마켓 정산', kind: 'settlement', day: 12, amount: 2_100_000, direction: 'in', partnerId: 'P2', delay: { mean: 3, sd: 3 } },
  { id: 'S3', label: '온누리푸드 정산', kind: 'settlement', day: 20, amount: 4_000_000, direction: 'in', partnerId: 'P3', delay: { mean: 1, sd: 2 } },
  { id: 'F1', label: '임대료', kind: 'fixed', day: 5, amount: 1_500_000, direction: 'out' },
  { id: 'F2', label: '인건비', kind: 'fixed', day: 10, amount: 3_200_000, direction: 'out' },
  { id: 'F3', label: '공과금', kind: 'fixed', day: 15, amount: 400_000, direction: 'out' },
  { id: 'Y1', label: '대성유통 매입 대금', kind: 'payable', day: 8, amount: 1_800_000, direction: 'out', partnerId: 'P4' },
  { id: 'Y2', label: '대성유통 매입 대금', kind: 'payable', day: 22, amount: 1_800_000, direction: 'out', partnerId: 'P4' },
  { id: 'L1', label: '운영자금대출 상환', kind: 'loan', day: 14, amount: 2_400_000, direction: 'out', loanId: 'L1', floatingRate: true },
  { id: 'L2', label: '시설자금대출 상환', kind: 'loan', day: 25, amount: 900_000, direction: 'out', loanId: 'L2' },
]

export interface PolicyProduct {
  name: string
  agency: string
  rate: string
  limit: string
}

export const policyProducts: PolicyProduct[] = [
  { name: '소상공인 긴급경영안정자금', agency: '소상공인시장진흥공단', rate: '연 3.0%', limit: '최대 7천만원' },
  { name: '새희망홀씨(사업자)', agency: '서민금융진흥원', rate: '연 4.5%', limit: '최대 3천만원' },
]

// 최근 7일 실제 일별 종료 잔액 (index 0 = 7일 전, 마지막 = 오늘 시작 잔액)
export const pastBalances: number[] = isRisk
  ? [4_150_000, 3_880_000, 3_940_000, 3_560_000, 3_420_000, 3_190_000, 3_030_000, business.startBalance]
  : [2_150_000, 2_480_000, 2_260_000, 2_790_000, 3_050_000, 2_870_000, 3_020_000, business.startBalance]

export interface NewsItem {
  id: string
  tag: '정책자금' | '금리' | '세무' | '업종'
  title: string
  source: string
  date: string
}

// 샘플 데이터: 실제 기사가 아니다. 뉴스 API 연동 시 교체한다.
const riskNews: NewsItem[] = [
  { id: 'N1', tag: '정책자금', title: '소상공인 긴급경영안정자금 접수 안내 (신속 심사)', source: '소상공인시장진흥공단', date: '10/1' },
  { id: 'N2', tag: '업종', title: '거래처 정산이 늦어질 때 단기 자금 메우는 방법', source: '금융뉴스', date: '10/1' },
  { id: 'N3', tag: '정책자금', title: '새희망홀씨(사업자) 한도·금리 비교 정보', source: '서민금융진흥원', date: '9/30' },
  { id: 'N4', tag: '금리', title: '기준금리 인상 가능성, 변동금리 대출 점검 포인트', source: '금융뉴스', date: '9/30' },
  { id: 'N5', tag: '세무', title: '부가가치세 납부 연기·분납 신청 안내', source: '금융뉴스', date: '9/29' },
  { id: 'N6', tag: '업종', title: '카드 결제 이연으로 현금흐름 완충하기', source: '금융뉴스', date: '9/27' },
]
const normalNews: NewsItem[] = [
  { id: 'N1', tag: '정책자금', title: '소상공인 긴급경영안정자금 접수 안내', source: '소상공인시장진흥공단', date: '10/1' },
  { id: 'N2', tag: '금리', title: '기준금리 동결 시 변동금리 대출 부담은?', source: '금융뉴스', date: '10/1' },
  { id: 'N3', tag: '세무', title: '부가가치세 신고·납부 일정 점검 포인트', source: '금융뉴스', date: '9/30' },
  { id: 'N4', tag: '업종', title: '식자재 도매 단가 동향과 매입 대금 관리', source: '금융뉴스', date: '9/29' },
  { id: 'N5', tag: '정책자금', title: '새희망홀씨(사업자) 금리 비교 정보', source: '서민금융진흥원', date: '9/28' },
  { id: 'N6', tag: '세무', title: '폐업·휴업 거래처 확인 방법 (국세청 상태조회)', source: '금융뉴스', date: '9/26' },
]
export const news: NewsItem[] = isRisk ? riskNews : normalNews

export const won =(n: number): string => {
  const sign = n < 0 ? '-' : ''
  const a = Math.abs(Math.round(n))
  if (a >= 10_000) return `${sign}${(a / 10_000).toLocaleString('ko-KR', { maximumFractionDigits: 0 })}만원`
  return `${sign}${a.toLocaleString('ko-KR')}원`
}

const TODAY = new Date('2026-10-01')
export const isoDay = (day: number): string => {
  const d = new Date(TODAY)
  d.setDate(d.getDate() + day)
  return d.toISOString().slice(0, 10)
}
export const dayLabel = (day: number): string => {
  const d = new Date(TODAY)
  d.setDate(d.getDate() + day)
  return `${d.getMonth() + 1}/${d.getDate()}`
}
