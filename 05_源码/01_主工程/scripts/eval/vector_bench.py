"""P1-2 评估：词袋余弦 vs 哈希向量检索，在真实演示语料上对比 Recall。

背景：《推进计划》P1-2 指出知识接入是词袋余弦（`knowledge_hub.py:1127 _tokenize`、
`:1141 _cosine`），不是向量检索。换成向量检索之前先量出差距——否则「改了」无法证明「更好」。

本脚本不动生产代码，只做离线对比：
- baseline：现有的分词 + 词袋余弦（复刻 `_tokenize` / `_cosine` 的做法）
- candidate：字符 3-gram 哈希向量（256 维，L2 归一化后点积）

语料：自动收集 `backend/data/files/demo/` 下的 .md，用「标题前若干词」当查询，
金标就是该文档本身，统计 Recall@1 / Recall@3。

用法：python scripts/eval/vector_bench.py
"""

from __future__ import annotations

import hashlib
import math
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]          # 01_主工程
CORPUS_DIR = ROOT / "backend" / "data" / "files" / "demo"
DIM = 256


def tokenize(text: str) -> list[str]:
    """复刻现有做法：中日韩按字切，其余按词切。"""
    text = text.lower()
    cjk = re.findall(r"[\u4e00-\u9fff]", text)
    words = re.findall(r"[a-z0-9]+", text)
    return cjk + words


def bag_cosine(a: str, b: str) -> float:
    ta, tb = tokenize(a), tokenize(b)
    if not ta or not tb:
        return 0.0
    da, db = {}, {}
    for tok in ta:
        da[tok] = da.get(tok, 0) + 1
    for tok in tb:
        db[tok] = db.get(tok, 0) + 1
    dot = sum(v * db.get(k, 0) for k, v in da.items())
    na = math.sqrt(sum(v * v for v in da.values()))
    nb = math.sqrt(sum(v * v for v in db.values()))
    return dot / (na * nb) if na and nb else 0.0


def embed(text: str) -> list[float]:
    """字符 3-gram 哈希向量，确定性、无需模型、可复现。"""
    vec = [0.0] * DIM
    cleaned = re.sub(r"\s+", "", text.lower())
    grams = [cleaned[i : i + 3] for i in range(max(1, len(cleaned) - 2))]
    for gram in grams:
        h = int(hashlib.md5(gram.encode()).hexdigest()[:8], 16)
        vec[h % DIM] += 1.0
    norm = math.sqrt(sum(v * v for v in vec))
    return [v / norm for v in vec] if norm else vec


def dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def main() -> int:
    if not CORPUS_DIR.exists():
        print(f"找不到语料目录：{CORPUS_DIR}")
        return 2
    docs = []
    for path in sorted(CORPUS_DIR.glob("*.md")):
        body = path.read_text(encoding="utf-8", errors="ignore")
        title_match = re.search(r"^#\s+(.+)$", body, re.M)
        title = title_match.group(1).strip() if title_match else path.stem
        docs.append({"id": path.stem, "title": title, "body": body})
    if len(docs) < 2:
        print(f"语料不足（{len(docs)} 篇），无法对比")
        return 2

    queries = [{"q": d["title"], "gold": d["id"]} for d in docs]
    vectors = {d["id"]: embed(d["title"] + "\n" + d["body"][:2000]) for d in docs}

    def recall(score_fn, k: int) -> float:
        hit = 0
        for item in queries:
            ranked = sorted(docs, key=lambda d: score_fn(item["q"], d), reverse=True)
            if item["gold"] in [d["id"] for d in ranked[:k]]:
                hit += 1
        return hit / len(queries)

    baseline = lambda q, d: bag_cosine(q, d["title"] + "\n" + d["body"][:2000])  # noqa: E731
    candidate = lambda q, d: dot(embed(q), vectors[d["id"]])  # noqa: E731

    print(f"corpus={len(docs)} queries={len(queries)} dim={DIM}")
    for k in (1, 3):
        b, c = recall(baseline, k), recall(candidate, k)
        mark = "candidate↑" if c > b else ("tie" if c == b else "candidate↓")
        print(f"Recall@{k}  bag_cosine={b:.2f}  hashed_vector={c:.2f}  {mark}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
