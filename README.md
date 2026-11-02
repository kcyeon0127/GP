# 상생여지도 (08조 졸업 프로젝트)

소상공인 대표자가 거래처·고정비·대출 일정을 등록하면 앞으로 4주 안에 언제 얼마가 모자라는지 미리 알려 주고, 그 이유를 거래관계(금융지도)와 계약 문서 근거로 보여 주는 서비스다. 설계 문서 링크는 [docs/README.md](docs/README.md).

## 구조

| 폴더 | 내용 |
| --- | --- |
| `backend/` | FastAPI 4계층 (api / services / repositories / domain), CashflowEngine, pytest |
| `frontend/` | React + TypeScript (Vite), Recharts 대시보드, Cytoscape.js 금융지도 |
| `docker-compose.yml` | PostgreSQL 16 + pgvector, Neo4j 5.26 |
| `docs/` | 양식 문서 링크, 설계 그림 원본 |

## 실행 (Sprint 1 시연)

```bash
docker compose up -d                                   # DB 2개
ssh -N -L 8101:127.0.0.1:8101 lab &                     # 연구실 서버 bge-m3 임베딩 API (근거 검색용)

cd backend
python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt
echo "EMBEDDING_API_KEY=<lab 서버 /root/sangsaeng/api_key>" > .env
.venv/bin/python -m scripts.seed_demo                  # 시연 사업장·계약 문서 적재, 그래프 동기화
.venv/bin/uvicorn app.main:app --reload --port 8000     # API 문서: http://localhost:8000/docs
.venv/bin/pytest -q                                     # 계산 정답 20건 포함 59건
.venv/bin/python -m scripts.eval_recall                # US-07 근거 재현율 (목표 80%)

cd ../frontend
npm ci && npm run dev                                   # http://localhost:5173
```

백엔드에 닿지 않으면 프론트는 합성 데이터 시연 화면으로 돌아간다.

## 연구실 서버 (lab)

`/root/sangsaeng`에 conda 환경 `sangsaeng`(vLLM 0.8.5). `serve.sh`는 sLLM(Qwen2.5-1.5B, 포트 8100, GPU 0), `serve_embed.sh`는 bge-m3 임베딩(포트 8101, GPU 1)을 띄운다. 둘 다 `screen -ls`로 확인한다.
