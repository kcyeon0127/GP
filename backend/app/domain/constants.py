HORIZON_DAYS = 84  # 12주 예측 구간 (기준일 = 1일째)
ALERT_DAYS = 28  # 4주 조기경보 구간

# US-18 경보 신뢰도: 요인별 배점(합 100)과 등급 경계. 점수 = 요인 점수 합.
CONF_W_PATH = 40  # 영향 일정 중 거래관계 경로(P 근거)가 있는 비율
CONF_W_CLAUSE = 30  # 영향 일정의 계약 중 문서 조항(D 근거)이 있는 비율 (질문 화면은 질문 해석 완전성)
CONF_W_LINK = 15  # 영향 일정 중 받는 곳·계약이 등록된 비율
CONF_W_INFLOW = 15  # 경보일 뒤 들어올 정산 일정이 등록되어 있는지
CONF_HIGH = 70  # 이상이면 높음
CONF_MEDIUM = 40  # 이상이면 보통, 미만이면 낮음 (대응안·설명 판단 보류)

# 근거 인용 설명
EXPLAIN_MAX_SENTENCES = 5
EXPLAIN_MAX_CHARS = 700
EXPLAIN_EVIDENCE_CHARS = 300  # 프롬프트에 넣는 근거 한 줄 최대 길이
