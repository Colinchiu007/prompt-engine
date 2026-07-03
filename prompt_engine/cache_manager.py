"""Cache management — L1 memory + L2 SQLite cache with fuzzy matching.

Extracted from optimizer.py God Class refactoring (Phase 1).
"""

import logging
from pathlib import Path
from typing import Optional

from prompt_engine.cache import SqlitePromptCache, MemoryPromptCache
from prompt_engine.models import OptimizeResult

logger = logging.getLogger(__name__)

# ── 内存缓存池（L1 热点缓存）
_PromptCacheKey = tuple[str, str, int, int, str, int]
_PromptCache: dict[_PromptCacheKey, OptimizeResult] = {}

# ── TF-IDF 向量化器（惰性初始化）
_VECTORIZER = None


def get_vectorizer():
    """Lazy-init TF-IDF vectorizer for similarity matching."""
    global _VECTORIZER
    if _VECTORIZER is None:
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            _VECTORIZER = TfidfVectorizer(analyzer="char", ngram_range=(2, 3))
        except ImportError:
            _VECTORIZER = False
    return _VECTORIZER if _VECTORIZER is not False else None


def _legacy_similarity(a: str, b: str) -> float:
    """旧版相似度（set inclusion），作为 TF-IDF 的降级"""
    a = a.strip().lower()
    b = b.strip().lower()
    if a == b:
        return 1.0
    a_words = set(a.split())
    b_words = set(b.split())
    if a_words & b_words:
        return 0.8
    return 0.5


def similarity(a: str, b: str) -> float:
    """TF-IDF 余弦相似度（降级到旧算法）"""
    if a.strip().lower() == b.strip().lower():
        return 1.0

    vec = get_vectorizer()
    if vec is None:
        return _legacy_similarity(a, b)

    try:
        import numpy as np
        tfidf = vec.fit_transform([a.strip().lower(), b.strip().lower()])
        sim = (tfidf * tfidf.T).A[0, 1]
        return float(sim)
    except Exception:
        return _legacy_similarity(a, b)


def fuzzy_match_prompt(
    prompt: str, platform: str, creative_level: int = 7,
    max_length: int = 500, negative_prompt: str = "",
    num_candidates: int = 1, similarity_threshold: float = 0.7,
) -> Optional[OptimizeResult]:
    """模糊匹配相似 prompt，命中缓存后返回"""
    normalized = prompt.strip().lower()
    best_result = None
    best_score = 0.0

    for (cached_p, cached_plat, cached_cl, cached_ml, cached_np, cached_nc), cached_res in _PromptCache.items():
        if cached_plat != platform:
            continue
        if cached_cl != creative_level or cached_ml != max_length or cached_np != negative_prompt or cached_nc != num_candidates:
            continue
        score = similarity(normalized, cached_p.lower())
        if score > best_score:
            best_score = score
            best_result = cached_res

    if best_score >= similarity_threshold:
        logger.info("Cache hit: %s @ %s (similarity: %.3f)", normalized, platform, best_score)
        return best_result

    return None


class CacheManager:
    """双级缓存管理器：L1 内存（MemoryPromptCache）+ L2 SQLite（SqlitePromptCache）"""

    def __init__(self):
        self._sqlite_cache = SqlitePromptCache()
        self._mem_cache = MemoryPromptCache()

    def make_key(
        self, prompt: str, platform: str, creative_level: int,
        max_length: int, negative_prompt: str, num_candidates: int,
    ) -> str:
        return SqlitePromptCache.make_key(
            prompt, platform, creative_level, max_length, negative_prompt, num_candidates,
        )

    def get(
        self, prompt: str, platform: str, creative_level: int,
        max_length: int, negative_prompt: str, num_candidates: int,
    ) -> Optional[OptimizeResult]:
        """双级缓存读取：L1 内存 → L2 SQLite（预热 L1）"""
        key = self.make_key(prompt, platform, creative_level, max_length, negative_prompt, num_candidates)
        # L1
        cached = self._mem_cache.get(key)
        if cached:
            return cached
        # L2
        cached = self._sqlite_cache.get(prompt, platform, creative_level, max_length, negative_prompt, num_candidates)
        if cached:
            self._mem_cache.set(key, cached)  # 预热 L1
            return cached
        return None

    def set(
        self, prompt: str, platform: str, creative_level: int,
        max_length: int, negative_prompt: str, num_candidates: int,
        result: OptimizeResult,
    ) -> None:
        """写入双级缓存"""
        key = self.make_key(prompt, platform, creative_level, max_length, negative_prompt, num_candidates)
        self._mem_cache.set(key, result)
        self._sqlite_cache.set(prompt, platform, creative_level, max_length, negative_prompt, num_candidates, result)
        # 同时写入旧版 dict 缓存（兼容 fuzzy_match_prompt）
        _PromptCache[(prompt.strip().lower(), platform, creative_level, max_length, negative_prompt, num_candidates)] = result

    @property
    def sqlite_cache(self) -> SqlitePromptCache:
        return self._sqlite_cache

    @property
    def mem_cache(self) -> MemoryPromptCache:
        return self._mem_cache
