"""TF-IDF 向量存储 — 跨引擎共享的轻量语义检索（免 sklearn 依赖）。

来源：视频引擎 knowledge/vector_store.py（手写 TF-IDF + 余弦相似度 + index.json 持久化），
原样提炼为通用实现，两引擎共用同一检索语义。
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any

# index.json 持久化格式版本：1=裸列表（历史格式），2={"version": N, "docs": [...]}
INDEX_VERSION = 2


def _tokenize(text: str) -> list[str]:
    text = str(text or "").lower()
    # 中英文分词：保留中文单字/词 + 英文词
    tokens = re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]{1,4}", text)
    return [t for t in tokens if len(t) >= 1]


class PromptVectorStore:
    """Prompt 检索库 — 手写 TF-IDF 语义检索，零下载、零第三方依赖。"""

    def __init__(
        self, persist_dir: str | Path, data_file: str = "index.json", default_platform: str = "generic_video",
    ):
        """default_platform：add_prompts 时条目缺 platform 的回退值（视频引擎历史语义；
        图片引擎如后续迁移需显式传图片默认平台）。"""
        self._dir = Path(persist_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._index_path = self._dir / data_file
        self._default_platform = default_platform
        self._docs: list[dict[str, Any]] = []
        self._built = False
        self._df: dict[str, int] = {}
        self._doc_vectors: list[dict[str, int]] = []
        self._doc_totals: list[int] = []
        self._doc_norms: list[float] = []
        self._loaded_version = 0  # 0=无文件/解析失败，1=历史裸列表格式
        self._load()
        # 冷启动主动建索引：把首次检索的 ~1.5s（730 条）成本移到进程启动，避免首请求卡顿
        self._ensure_index()

    def _load(self):
        if self._index_path.exists():
            try:
                data = json.loads(self._index_path.read_text(encoding="utf-8"))
                if isinstance(data, dict) and "docs" in data:
                    self._docs = data["docs"]
                    self._loaded_version = int(data.get("version", 0))
                elif isinstance(data, list):
                    self._docs = data
                    self._loaded_version = 1  # 历史裸列表格式
                else:
                    self._docs = []
            except Exception:
                self._docs = []

    def save(self):
        payload = {"version": INDEX_VERSION, "docs": self._docs}
        self._index_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    @property
    def schema_version(self) -> int:
        """当前加载的持久化格式版本（0=无文件/解析失败，1=历史裸列表，2=当前）。"""
        return self._loaded_version

    @property
    def count(self) -> int:
        return len(self._docs)

    def _invalidate_index(self):
        """索引缓存失效：种子变更后下次 search 重建 df/文档向量。"""
        self._built = False
        self._df = {}
        self._doc_vectors = []
        self._doc_totals = []
        self._doc_norms = []

    def _ensure_index(self):
        """预计算 df + 每篇文档词项计数与范数（O(total_tokens) 单次构建）。

        修复历史 O(n²·len)：旧 _tfidf 对每个查询 term 全量 tokenize 所有文档、
        search 又对每篇文档重复计算（140 条种子实测 ~119s/查询）。
        """
        if self._built:
            return
        df: dict[str, int] = {}
        vectors: list[dict[str, int]] = []
        totals: list[int] = []
        for doc in self._docs:
            tokens = _tokenize(doc.get("document", ""))
            counter: dict[str, int] = {}
            for t in tokens:
                counter[t] = counter.get(t, 0) + 1
            vectors.append(counter)
            totals.append(len(tokens))
            for t in counter:
                df[t] = df.get(t, 0) + 1
        n = max(1, len(self._docs))
        norms: list[float] = []
        for counter, total in zip(vectors, totals):
            if total == 0:
                norms.append(0.0)
                continue
            norm = 0.0
            for t, count in counter.items():
                idf = math.log((n + 1) / (df.get(t, 0) + 1)) + 1
                w = (count / total) * idf
                norm += w * w
            norms.append(math.sqrt(norm))
        self._df = df
        self._doc_vectors = vectors
        self._doc_totals = totals
        self._doc_norms = norms
        self._built = True

    def clear(self):
        self._docs = []
        self._invalidate_index()
        self.save()

    def add_prompts(self, entries: list[Any]):
        for e in entries:
            doc = {
                "id": getattr(e, "id", ""),
                "title": getattr(e, "title", ""),
                "description": getattr(e, "description", ""),
                "document": getattr(e, "prompt_text", ""),
                "language": getattr(e, "language", "en"),
                "platform": getattr(e, "platform", None) or self._default_platform,
                "style": getattr(e, "style", ""),
                "categories": list(getattr(e, "categories", [])),
                "quality_score": getattr(e, "quality_score", 5),
                "source": getattr(e, "source", ""),
            }
            self._docs.append(doc)
        self._invalidate_index()
        self.save()

    def _tfidf(self, tokens: list[str]) -> dict[str, float]:
        # legacy：仅测试作参考实现（O(n²)，生产路径走预计算索引 search）
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
        """向量检索（预计算索引路径，结果与旧 _tfidf/_cosine 逐位一致）。

        - 查询向量：df 来自预计算索引（与旧算法 same 全库 df）
        - 文档权重：预计算词项计数 + 预计算范数，余弦 = dot/(qnorm*doc_norm)
        """
        self._ensure_index()
        n = max(1, len(self._docs))
        tokens = _tokenize(query)
        total = len(tokens)
        if total == 0:
            return []
        qcounter: dict[str, int] = {}
        for t in tokens:
            qcounter[t] = qcounter.get(t, 0) + 1
        qvec: dict[str, float] = {}
        for term, count in qcounter.items():
            df = self._df.get(term, 0)
            qvec[term] = (count / total) * (math.log((n + 1) / (df + 1)) + 1)
        qnorm = math.sqrt(sum(v * v for v in qvec.values()))
        scored = []
        # zip 迭代消除下标交叉（W3）：并发 add/clear 导致 _docs 长度变化时不会 IndexError
        for doc, counter, doc_total, doc_norm in zip(
            self._docs, self._doc_vectors, self._doc_totals, self._doc_norms,
        ):
            if platform and doc.get("platform") != platform and doc.get("platform") != "generic_video":
                continue
            if doc_total == 0:
                continue
            dot = 0.0
            for term, qw in qvec.items():
                c = counter.get(term)
                if c:
                    df = self._df.get(term, 0)
                    dot += qw * (c / doc_total) * (math.log((n + 1) / (df + 1)) + 1)
            if dot == 0.0:
                continue
            score = dot / (qnorm * doc_norm) if qnorm and doc_norm else 0.0
            if score > 0:
                scored.append((score, doc))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [dict(doc, score=round(s, 4)) for s, doc in scored[:top_k]]

    def all_entries(self) -> list[dict[str, Any]]:
        return list(self._docs)

    def stats(self) -> dict[str, Any]:
        return {"entries": len(self._docs), "path": str(self._index_path)}
