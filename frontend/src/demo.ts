// 데모 변형: 빌드 때 VITE_DEMO로 고른다. 화면 구조는 같고 합성 데이터의 "상황"만 다르다.
//   normal(기본): 자금 상태 안정    risk: 한빛식자재 정산 지연이 확정되어 자금 상태가 위험한 상황
// 브라우저(Vite)와 Node(테스트) 양쪽에서 읽을 수 있게 둘 다 확인한다.
const viteEnv = (import.meta as unknown as { env?: Record<string, string | undefined> }).env
const nodeEnv = (globalThis as { process?: { env?: Record<string, string | undefined> } }).process?.env
export const DEMO: 'normal' | 'risk' = (viteEnv?.VITE_DEMO ?? nodeEnv?.VITE_DEMO) === 'risk' ? 'risk' : 'normal'
export const isRisk = DEMO === 'risk'

// 자연어 시뮬레이션 예시 질문(상황에 맞게 다르다)
export const EXAMPLES: string[] = isRisk
  ? [
      '500만원 정책대출을 받으면 부족한 자금이 해소될까?',
      '다음 달 매출이 20% 줄면 어떻게 돼?',
      '금리가 1%p 오르면 상환 부담이 얼마나 늘어?',
      '청춘마켓이 폐업하면 어떻게 돼?',
    ]
  : [
      '한빛식자재 정산이 2주 밀리면 대출 갚을 수 있어?',
      '다음 달 매출이 20% 줄면 어떻게 돼?',
      '금리가 1%p 오르면 상환 부담이 얼마나 늘어?',
      '500만원 정책대출을 받으면 다음 상환 때 괜찮을까?',
    ]