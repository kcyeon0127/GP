프로젝트 문서 기록장입니다.

[양식 1] 디자인개요서 양식
https://docs.google.com/document/d/1aRXT0sTcOneoEGpw1v9zdwSPrfwcBbcfeDPAs_cpqpM/edit?tab=t.0

---

[양식 2] 문제점목록 양식
https://docs.google.com/document/d/1gxLoUHymUSowHtozT8v7SvnZoIPgNFGxRXe3pn5Sw2Q/edit?usp=sharing

[발표자료]
https://canva.link/qqh335gg8eygmfl

---

[양식 3] 아이디에이션 결과보고서
https://docs.google.com/document/d/1cfB0cU59x_uykWun-79yndpFaG4xlXpXsj2WVWSK77c/edit?usp=sharing

---

[양식 4] 문제정의서 양식
https://docs.google.com/document/d/1MPfkRvoL_vhu5ddrBYVVQGAB7X8FLjinxJJNjsLvnuw/edit?usp=sharing


[발표자료]
https://canva.link/h4172o0o8jlt1q7

---


[양식 5] Product Backlog 양식
https://docs.google.com/document/d/1ha4jypcXW3L2wTz2sfwYg7ASTuNxQPA8HpR8s8UShtE/edit?usp=sharing

구글 드라이브 추가 자료 
https://drive.google.com/drive/folders/1C2bSWMLEN7DSiAAfw0CYIQHPsGcKK_4Z?usp=sharing

[발표자료]
https://canva.link/adfmg8pg6j795s7

---

[양식 6] 시스템 구조 설계 및 개발 환경 양식 (v1.3, 2026-10-31: 실제 구현 버전·임베딩 서빙·계산 규칙 반영)
https://docs.google.com/document/d/1GEoUsomNmimgjNj-gOL3PDdCISJfDo_irU6Clihp8Po/edit?usp=sharing

[발표자료]

---

[양식 7-1] Sprint Planning (Sprint 1: 2026.10.26 ~ 11.20, US-01~07, 41 SP)
https://docs.google.com/document/d/13huh-leDCQWCsKxJyxOKmHT78RMbThDLOvADD-vVkRU/edit?usp=sharing

[양식 7-2] Sprint Backlog (Task 28개 상태, DoD 결과)
https://docs.google.com/document/d/1nEYjC1LvDHLeroL29KqfdHv0PZI0LNSct_2dDeXKrDQ/edit?usp=sharing

---

## Sprint 1 구현 메모 (양식 6 v1.3과 같은 내용)

- 계산 규칙: 기준일이 1일째, 84일(12주) 계산, 같은 날 입출금은 하루 합계, 0원 미만이 부족, 4주 안 0원 미만 빨강·안전 잔액 미만 노랑. 기준 정답 20건은 `backend/tests/fixtures/cashflow/`
- 근거 ID: P = 거래관계 경로(Neo4j), D = 계약 문서 조각(pgvector). 번호는 먼저 막히는 지급 순서
- 테이블: 계약 문서는 `document`·`document_chunk` 두 테이블, `response_plan`은 Sprint 2(US-10)에서 추가
- 임베딩 bge-m3·sLLM Qwen2.5-1.5B는 연구실 서버 vLLM으로 서빙 (실행 방법은 루트 README)
- 프론트 버전: React 19, TypeScript 6, Vite 8, Recharts 2.15, Cytoscape.js 3.34
