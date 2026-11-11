# What-if Tasks (US-08 · US-09)

동작 기준: [spec.md](spec.md)

- Task ID: US-09는 양식 7-2 (Rev 10, 11/04) 그대로
- US-08은 11/10 7-2에 추가된 T36~T39 (이전 임시 ID S2-T1~S2-T4)
- 상태·잔여는 7-2가 원본. 이 파일은 AC 검증 기록용이며 7-2를 대신하지 않음

## 1. Task 목록

### US-09 What-if 시나리오 조정·비교 (8 SP, Sprint 1)

| ID | Task | 담당 | Est(h) | 관련 AC | 상태 | PR |
|---|---|---|---|---|---|---|
| T32 | 정산 지연·매출 감소·원가 상승 규칙 구현 | 김채연 | 8 | AC-04·05·06 | 병합, 7-2 판정 대기 | #14 |
| T33 | 금리 상승 규칙 구현 | 김채연 | 3 | AC-03 | 병합, 7-2 판정 대기 | #14 |
| T34 | 시나리오 API·새 부족 지급 추출 | 김채연 | 4 | AC-02·03·07 | 병합, 7-2 판정 대기 | #14 |
| T35 | What-if 입력 화면·곡선 비교 작성 | 김채연 | 5 | AC-01·07 | 병합, 7-2 판정 대기 | #14 |

### US-08 위험 영향 경로 강조 (8 SP, Sprint 1)

| ID | Task | 담당 | Est(h) | 관련 AC | 상태 | PR |
|---|---|---|---|---|---|---|
| T36 | 영향 경로 Cypher 질의 구현 | 이승훈 | 6 | AC-01·02 | 리뷰 대기 | - |
| T37 | 영향 경로 API 작성 | 이승훈 | 3 | AC-03 | 리뷰 대기 | - |
| T38 | 경로 강조·번호·흐림 화면 작성 | 김채연 | 6 | AC-01·05 | 리뷰 대기 | - |
| T39 | 단계 상세 패널·시나리오 전환 작성 | 김채연 | 4 | AC-04·06 | 리뷰 대기 | - |

## 2. AC 검증 기록

태스크 완료 시 관련 AC 행을 채운다. 결과는 P(Pass) / F(Fail) / 보류.

### US-09

| AC | Task | 검증 방법 | 결과 | 확인일 | 비고 |
|---|---|---|---|---|---|
| AC-01 | T35 | 화면 확인 | 보류 | - | PR #14 병합, 7-2 판정 대기 |
| AC-02 | T34 | pytest test_api_delay_new_shortage_ac02 | 보류 | - | PR #14 병합, 7-2 판정 대기 |
| AC-03 | T33, T34 | pytest test_api_four_scenarios_ac03 | 보류 | - | PR #14 병합, 7-2 판정 대기 |
| AC-04 | T32 | pytest test_revenue_drop_ac04 | 보류 | - | PR #14 병합, 7-2 판정 대기 |
| AC-05 | T32 | pytest test_cost_rise_ac05_only_purchases | 보류 | - | PR #14 병합, 7-2 판정 대기 |
| AC-06 | T32 | pytest test_original_unchanged_ac06 | 보류 | - | PR #14 병합, 7-2 판정 대기 |
| AC-07 | T34, T35 | pytest test_api_range_ac07 + 화면 범위 안내 | 보류 | - | PR #14 병합, 7-2 판정 대기 |

### US-08

| AC | Task | 검증 방법 | 결과 | 확인일 | 비고 |
|---|---|---|---|---|---|
| AC-01 | T36, T38 | pytest test_delay_path_order_ac01_ac02, test_api_impact_path_ac01_ac06 + 화면 확인 | 보류 | - | 병합 전 |
| AC-02 | T36 | pytest test_delay_path_order_ac01_ac02 | 보류 | - | 병합 전 |
| AC-03 | T37 | pytest test_no_risk_empty_path_ac03 + 화면 확인 | 보류 | - | 병합 전 |
| AC-04 | T39 | pytest test_evidence_ids_follow_path_ac04 + 화면 확인 | 보류 | - | 병합 전 |
| AC-05 | T38 | 화면 확인 | 보류 | - | 병합 전 |
| AC-06 | T39 | pytest test_api_impact_path_ac01_ac06 + 화면 확인 | 보류 | - | 병합 전 |

## 3. 기록 규칙

- 결과는 main 병합 후 확인한 것만 P/F로 적는다 (병합 전은 보류)
- 비고에 PR 번호 또는 테스트 실행 시각을 남긴다
- 7-2 DoD Mapping과 결과가 다르면 7-2를 기준으로 맞추고, 7-2 수정은 팀원이 직접 한다
