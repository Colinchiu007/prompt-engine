"""v0.19.0 F1 — SQLite 缓存持久化测试"""
import os, sys, tempfile, time, json
from pathlib import Path

import pytest

from prompt_engine.models import OptimizeResult, PlatformType, StyleType


class TestSqliteCacheBasic:
    """SQLite 缓存基本读写"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """用临时 DB 避免污染真实数据"""
        self.tmp_db = tempfile.mktemp(suffix=".db")
        # patch SqlitePromptCache to use tmp db
        import prompt_engine.cache as cache_mod
        self._orig_path = getattr(cache_mod.SqlitePromptCache, "DB_PATH", None)
        # 注入临时路径
        self.cache = cache_mod.SqlitePromptCache(db_path=self.tmp_db, ttl_hours=48)
        yield
        self.cache.close()
        if os.path.exists(self.tmp_db):
            os.unlink(self.tmp_db)

    def _make_result(self, text: str) -> OptimizeResult:
        return OptimizeResult(
            optimized_prompt=text,
            platform=PlatformType.MIDJOURNEY,
            style=StyleType.REALISTIC,
            model_used="test",
            tokens_used=100,
            duration_ms=500,
        )

    def test_set_and_get(self):
        """写入后能读取"""
        result = self._make_result("a majestic cat --ar 16:9 --v 6.1")
        self.cache.set("test prompt", "midjourney", 7, 500, "", 1, result)

        got = self.cache.get("test prompt", "midjourney", 7, 500, "", 1)
        assert got is not None
        assert got.optimized_prompt == "a majestic cat --ar 16:9 --v 6.1"
        assert got.tokens_used == 0  # 缓存命中时 tokens=0
        assert got.duration_ms == 0
        assert got.platform == PlatformType.MIDJOURNEY

    def test_miss_returns_none(self):
        """不存在的 key 返回 None"""
        got = self.cache.get("nonexistent", "midjourney", 7, 500, "", 1)
        assert got is None

    def test_different_platform_is_miss(self):
        """相同 prompt 不同 platform 视为不同缓存"""
        result = self._make_result("mj style")
        self.cache.set("test", "midjourney", 7, 500, "", 1, result)
        got = self.cache.get("test", "stable_diffusion", 7, 500, "", 1)
        assert got is None

    def test_different_creative_level_is_miss(self):
        """不同 creative_level 视为不同缓存"""
        result = self._make_result("creative")
        self.cache.set("test", "midjourney", 7, 500, "", 1, result)
        got = self.cache.get("test", "midjourney", 5, 500, "", 1)
        assert got is None

    def test_restart_survives(self):
        """关闭后重新打开，相同 key 仍能命中"""
        result = self._make_result("persistent data")
        self.cache.set("survive", "midjourney", 7, 500, "", 1, result)
        self.cache.close()

        # 新实例读同一文件
        import prompt_engine.cache as cache_mod
        cache2 = cache_mod.SqlitePromptCache(db_path=self.tmp_db, ttl_hours=48)
        try:
            got = cache2.get("survive", "midjourney", 7, 500, "", 1)
            assert got is not None
            assert got.optimized_prompt == "persistent data"
        finally:
            cache2.close()


class TestSqliteCacheTTL:
    """TTL 过期清理"""

    @pytest.fixture(autouse=True)
    def setup(self):
        import prompt_engine.cache as cache_mod
        self.tmp_db = tempfile.mktemp(suffix=".db")
        self.cache = cache_mod.SqlitePromptCache(db_path=self.tmp_db, ttl_hours=0.001)  # ~3.6s
        yield
        self.cache.close()
        if os.path.exists(self.tmp_db):
            os.unlink(self.tmp_db)

    def _make_result(self, text: str) -> OptimizeResult:
        return OptimizeResult(
            optimized_prompt=text,
            platform=PlatformType.MIDJOURNEY,
            style=StyleType.REALISTIC,
            model_used="test",
            tokens_used=100,
            duration_ms=500,
        )

    def test_ttl_expiry(self):
        """TTL 过期后 vacuum 清理"""
        self.cache.set("old", "midjourney", 7, 500, "", 1, self._make_result("old data"))
        # TTL 只有 ~3.6s，等过期
        time.sleep(4)
        before = self.cache.stats()
        assert before["entries"] == 1  # vacuum 前还在

        self.cache.vacuum()
        after = self.cache.stats()
        assert after["entries"] == 0  # vacuum 后清掉


class TestMemoryCache:
    """L1 内存缓存"""

    def test_memory_cache_eviction(self):
        from prompt_engine.cache import MemoryPromptCache
        mc = MemoryPromptCache(max_entries=3)
        for i in range(5):
            mc.set(f"key{i}", OptimizeResult(
                optimized_prompt=f"prompt{i}", platform=PlatformType.MIDJOURNEY,
                style=StyleType.REALISTIC, model_used="test", tokens_used=10, duration_ms=100
            ))
        # 前 2 个应被淘汰
        assert mc.get("key0") is None
        assert mc.get("key1") is None
        # 后 3 个应还在
        assert mc.get("key2") is not None
        assert mc.get("key3") is not None
        assert mc.get("key4") is not None
