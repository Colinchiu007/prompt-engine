"""向量存储 — TF-IDF + 余弦相似度（轻量，免下载模型）"""
import json
from pathlib import Path
from typing import Optional
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from prompt_engine.knowledge.loader import PromptEntry


class PromptVectorStore:
    """Prompt 检索库 — TF-IDF 语义检索，零下载"""

    def __init__(self, persist_dir: str):
        self._persist_dir = Path(persist_dir)
        self._persist_dir.mkdir(parents=True, exist_ok=True)
        self._vectorizer = TfidfVectorizer(
            max_features=2000,
            stop_words=None,           # 停用词集加载太慢
            ngram_range=(1, 1),        # 只用 unigram，n-gram 组合爆炸
        )
        self._entries: list[PromptEntry] = []
        self._tfidf_matrix = None
        self._loaded = False
        self._load()

    def _data_path(self) -> Path:
        return self._persist_dir / "prompts.json"

    def _load(self):
        """从磁盘加载已保存的向量"""
        path = self._data_path()
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._entries = [PromptEntry(**e) for e in data]
            self._rebuild_index()
            self._loaded = True

    def _save(self):
        """保存到磁盘"""
        data = [
            {
                "id": e.id, "title": e.title, "description": e.description,
                "prompt_text": e.prompt_text, "language": e.language,
                "categories": e.categories, "platform": e.platform,
                "style": e.style, "quality_score": e.quality_score,
            }
            for e in self._entries
        ]
        with open(self._data_path(), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _rebuild_index(self):
        """重建 TF-IDF 索引"""
        if not self._entries:
            self._tfidf_matrix = None
            return
        texts = [f"{e.title} {e.description} {e.prompt_text}" for e in self._entries]
        self._tfidf_matrix = self._vectorizer.fit_transform(texts)

    @property
    def count(self) -> int:
        return len(self._entries)

    def add_prompts(self, prompts: list[PromptEntry]):
        """批量添加 prompt"""
        self._entries.extend(prompts)
        self._rebuild_index()
        self._save()

    def search(
        self,
        query: str,
        top_k: int = 3,
        platform: Optional[str] = None,
    ) -> list[dict]:
        """搜索相似 prompt"""
        if not self._entries or self._tfidf_matrix is None:
            return []

        # 按平台过滤
        if platform and platform != "generic":
            filtered_indices = [
                i for i, e in enumerate(self._entries) if e.platform == platform
            ]
            if not filtered_indices:
                filtered_indices = list(range(len(self._entries)))
        else:
            filtered_indices = list(range(len(self._entries)))

        # TF-IDF 向量化查询
        query_vec = self._vectorizer.transform([query])
        similarities = cosine_similarity(query_vec, self._tfidf_matrix[filtered_indices])[0]

        # 取 top_k
        top_idx = similarities.argsort()[::-1][:top_k]
        results = []
        for idx in top_idx:
            original_idx = filtered_indices[idx]
            entry = self._entries[original_idx]
            results.append({
                "id": entry.id,
                "document": entry.prompt_text,
                "metadata": {
                    "title": entry.title,
                    "description": entry.description,
                    "language": entry.language,
                    "platform": entry.platform,
                    "style": entry.style,
                    "categories": ",".join(entry.categories),
                },
                "distance": float(1 - similarities[idx]),
            })
        return results

    def clear(self):
        """清空库"""
        self._entries = []
        self._tfidf_matrix = None
        self._vectorizer = TfidfVectorizer(
            max_features=2000, stop_words=None, ngram_range=(1, 1),
        )
        path = self._data_path()
        if path.exists():
            path.unlink()