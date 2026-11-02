"""T23 Spike: bge-m3로 계약 문서 조각 검색이 쓸 만한지 확인한다.

계약서 10건(조각 24개, 합성)과 질문 20개(정답 조각 ID 포함)로 recall@k와 MRR을 잰다.
비교 기준으로 글자 2-gram 겹침 검색을 같이 돌린다. pgvector 적재는 T24에서 한다.
실행 (lab 서버): CUDA_VISIBLE_DEVICES=1 python run_spike.py
"""
import json
import time
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

HERE = Path(__file__).parent
docs = json.loads((HERE / "corpus.json").read_text())
queries = json.loads((HERE / "queries.json").read_text())
ids, texts = [], []
for d in docs:
    for i, c in enumerate(d["chunks"], 1):
        ids.append(f"{d['doc']}-{i}")
        texts.append(f"{d['title']} {c}")


def bigrams(s):
    s = s.replace(" ", "")
    return {s[i:i + 2] for i in range(len(s) - 1)}


def evaluate(rank_fn, name):
    rows, rec1, rec3, rec5, mrr = [], [], [], [], []
    for q in queries:
        order, scores = rank_fn(q["q"])
        top = [ids[i] for i in order[:5]]
        gold = set(q["gold"])
        if gold:
            hit = lambda k: len(gold & set(top[:k])) / len(gold)
            rec1.append(hit(1)); rec3.append(hit(3)); rec5.append(hit(5))
            first = next((r for r, i in enumerate(top, 1) if i in gold), None)
            mrr.append(1 / first if first else 0)
        rows.append(dict(q=q["q"], gold=q["gold"], top5=top, top1_score=round(float(scores[order[0]]), 3)))
    summary = dict(method=name, recall_at_1=np.mean(rec1), recall_at_3=np.mean(rec3), recall_at_5=np.mean(rec5), mrr=np.mean(mrr))
    return summary, rows


model = SentenceTransformer("BAAI/bge-m3", device="cuda")
model.half()
t = time.time()
emb = model.encode(texts, normalize_embeddings=True)
enc_ms = (time.time() - t) * 1000


def dense(q):
    v = model.encode([q], normalize_embeddings=True)[0]
    s = emb @ v
    return np.argsort(-s), s


def lexical(q):
    qb = bigrams(q)
    s = np.array([len(qb & bigrams(t)) / (len(qb) or 1) for t in texts])
    return np.argsort(-s, kind="stable"), s


out = {"dim": int(emb.shape[1]), "chunks": len(texts), "encode_ms_all_chunks": round(enc_ms)}
for fn, name in [(dense, "bge-m3"), (lexical, "char-bigram")]:
    summary, rows = evaluate(fn, name)
    out[name] = {"summary": {k: (round(v, 3) if isinstance(v, float) else v) for k, v in summary.items()}, "per_query": rows}
(HERE / "result.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
for name in ["bge-m3", "char-bigram"]:
    print(out[name]["summary"])
