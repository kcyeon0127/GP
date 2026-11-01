"""T27: 평가 질문 20건으로 근거 검색의 필수 근거 평균 재현율을 잰다 (US-07 AC-01, 목표 80% 이상).

실행 (backend 폴더, seed_demo 이후): .venv/bin/python -m scripts.eval_recall
재현율 = 상위 3개 근거 안에 든 필수 근거 수 / 필수 근거 수. 필수 근거가 없는 질문은 "근거 없음"이 맞았는지만 따로 센다.
"""
import json
from pathlib import Path

from app.db import SessionLocal
from app.repositories.business import get_or_create
from app.services.evidence_service import search_question

K = 3
QUESTIONS = json.loads((Path(__file__).resolve().parent.parent / "data" / "eval_questions.json").read_text())


def main():
    recalls, empty_ok, empty_n = [], 0, 0
    with SessionLocal() as s:
        bid = get_or_create(s).business_id
        for q in QUESTIONS:
            got = search_question(s, bid, q["question"], k=K)
            if q["required"]:
                r = len(set(q["required"]) & set(got)) / len(q["required"])
                recalls.append(r)
                mark = "O" if r == 1 else ("△" if r else "X")
            else:
                empty_n += 1
                ok = not got
                empty_ok += ok
                mark = "O" if ok else "X(근거 없음이어야 함)"
            print(f"{q['id']} {mark:3} 필수={q['required']} 검색={got}  {q['question']}")
    avg = sum(recalls) / len(recalls)
    print(f"\n필수 근거 평균 재현율@{K}: {avg:.1%} ({len(recalls)}문항)  목표 80% {'통과' if avg >= 0.8 else '미달'}")
    print(f"근거 없음 질문: {empty_ok}/{empty_n} 정답")


if __name__ == "__main__":
    main()
