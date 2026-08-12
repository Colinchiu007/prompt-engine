"""视频知识库 TF-IDF 向量存储（独立实现，机制复刻图片引擎 PromptVectorStore）。

- 独立持久化目录（video_prompts_db），不加载图片种子
- TF-IDF 检索 + platform 过滤
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any


def _tokenize(text: str) -> list[str]:
    text = str(text or "").lower()
    # 中英文分词：保留中文单字/词 + 英文词
    tokens = re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]{1,4}", text)
    return [t for t in tokens if len(t) >= 1]


class PromptVectorStore:
    def __init__(self, persist_dir: str | Path):
        self._dir = Path(persist_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._index_path = self._dir / "index.json"
        self._docs: list[dict[str, Any]] = []
        self._load()

    def _load(self):
        if self._index_path.exists():
            try:
                self._docs = json.loads(self._index_path.read_text(encoding="utf-8"))
            except Exception:
                self._docs = []

    def save(self):
        self._index_path.write_text(json.dumps(self._docs, ensure_ascii=False), encoding="utf-8")

    @property
    def count(self) -> int:
        return len(self._docs)

    def clear(self):
        self._docs = []
        self.save()

    def add_prompts(self, entries: list[Any]):
        for e in entries:
            doc = {
                "id": getattr(e, "id", ""),
                "title": getattr(e, "title", ""),
                "description": getattr(e, "description", ""),
                "document": getattr(e, "prompt_text", ""),
                "language": getattr(e, "language", "en"),
                "platform": getattr(e, "platform", "generic_video"),
                "style": getattr(e, "style", ""),
                "categories": list(getattr(e, "categories", [])),
                "quality_score": getattr(e, "quality_score", 5),
                "source": getattr(e, "source", ""),
            }
            self._docs.append(doc)
        self.save()

    def _tfidf(self, tokens: list[str]) -> dict[str, float]:
        total = len(tokens)
        if total == 0:
            return {}
        tf = Counter(tokens)
        n = max(1, len(self._docs))
        vec = {}
        for term, count in tf.items():
            df = sum(1 for d in self._docs if term in _tokenize(d.get("document", "")))
            idf = math.log((n + 1) / (df + 1)) + 1
            vec[term] = (count / total) * idf
        return vec

    @staticmethod
    def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
        if not a or not b:
            return 0.0
        common = set(a) & set(b)
        dot = sum(a[t] * b[t] for t in common)
        na = math.sqrt(sum(v * v for v in a.values()))
        nb = math.sqrt(sum(v * v for v in b.values()))
        return dot / (na * nb) if na and nb else 0.0

    def search(self, query: str, top_k: int = 3, platform: str | None = None) -> list[dict[str, Any]]:
        qvec = self._tfidf(_tokenize(query))
        scored = []
        for doc in self._docs:
            if platform and doc.get("platform") != platform and doc.get("platform") != "generic_video":
                continue
            score = self._cosine(qvec, self._tfidf(_tokenize(doc.get("document", ""))))
            if score > 0:
                scored.append((score, doc))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [dict(doc, score=round(s, 4)) for s, doc in scored[:top_k]]
