"""Round3 Batch A T1 — 图片主缓存 key 全组件化（修复串号缺陷）回归测试。

覆盖（REQ-1.5）：
- make_key 单测：同参异 excluded/no_swap/context/style/language → key 不同，全同 → 相同
- 版本盐：key 含 IMAGE_FMT_V1；旧格式（无盐）不再命中
- 集成级：同参异 excluded_characters 的两次 optimize() 第二次必须 cache miss
- fuzzy 零回归：legacy _PromptCache tuple 键/fuzzy_match_prompt 不受影响
"""
from __future__ import annotations

import tempfile
import uuid
from unittest.mock import patch

from prompt_engine.cache import SqlitePromptCache
from prompt_engine.models import OptimizeRequest, PlatformType, StyleType
from prompt_engine.optimizer import Optimizer
from prompt_engine.cache_manager import fuzzy_match_prompt

BASE = dict(
    prompt="a majestic cat in the rain",
    platform="midjourney",
    creative_level=7,
    max_length=500,
    negative_prompt="",
    num_candidates=1,
)


def _key(**overrides):
    kw = dict(BASE)
    kw.update(overrides)
    return SqlitePromptCache.make_key(**kw)


class TestMakeKeyComponents:
    def test_same_args_same_key(self):
        assert _key() == _key()

    def test_excluded_characters_changes_key(self):
        assert _key(excluded_characters=["JAX"]) != _key(excluded_characters=[])
        assert _key(excluded_characters=["JAX"]) != _key(excluded_characters=["MIA"])

    def test_no_swap_pairs_changes_key(self):
        assert _key(no_swap_pairs=[["A", "B"]]) != _key(no_swap_pairs=[])
        assert _key(no_swap_pairs=[["A", "B"]]) != _key(no_swap_pairs=[["A", "C"]])

    def test_context_changes_key(self):
        assert _key(context={"synopsis": "war"}) != _key(context=None)
        assert _key(context={"synopsis": "war"}) != _key(context={"synopsis": "peace"})
        # 键序无关：同内容不同顺序 → 相同 key
        assert _key(context={"a": 1, "b": 2}) == _key(context={"b": 2, "a": 1})

    def test_style_changes_key(self):
        assert _key(style=None) != _key(style="realistic")
        assert _key(style="realistic") != _key(style="oil_painting")

    def test_language_changes_key(self):
        assert _key(language="en") != _key(language="zh")

    def test_version_salt_present(self):
        key = _key()
        assert "IMAGE_FMT_V1" in key

    def test_old_sha256_format_no_longer_matches(self):
        # 旧实现：sha256(prompt|platform|...)，新 key 必须与旧格式不同（旧缓存自然失效）
        import hashlib
        old = hashlib.sha256(
            f"{BASE['prompt']}|{BASE['platform']}|{BASE['creative_level']}|{BASE['max_length']}|{BASE['negative_prompt']}|{BASE['num_candidates']}".encode("utf-8")
        ).hexdigest()
        assert _key() != old


class TestOptimizeCacheMiss:
    @staticmethod
    def _unique_prompt():
        return f"a cat in the rain {uuid.uuid4().hex[:8]}"

    @patch.object(Optimizer, "_call_llm")
    def test_excluded_differs_second_is_cache_miss(self, mock_call):
        mock_call.return_value = ("optimized prompt A", 100)
        o = Optimizer()
        prompt = self._unique_prompt()

        req_a = OptimizeRequest(
            prompt=prompt,
            platform=PlatformType.GENERIC,
            creative_level=7,
            excluded_characters=["JAX"],
        )
        req_b = OptimizeRequest(
            prompt=prompt,
            platform=PlatformType.GENERIC,
            creative_level=7,
            excluded_characters=[],
        )
        r_a = o.optimize(req_a)
        r_b = o.optimize(req_b)
        assert not r_a.error and not r_b.error
        # 两次都走 LLM → 第二次不是缓存命中（串号被修复）
        assert mock_call.call_count == 2

    @patch.object(Optimizer, "_call_llm")
    def test_same_request_second_is_cache_hit(self, mock_call):
        mock_call.return_value = ("optimized prompt A", 100)
        o = Optimizer()
        req = OptimizeRequest(
            prompt=self._unique_prompt(),
            platform=PlatformType.GENERIC,
            creative_level=7,
            excluded_characters=["JAX"],
            context={"synopsis": "war"},
            style=StyleType.REALISTIC,
        )
        o.optimize(req)
        r2 = o.optimize(req)
        # 缓存命中：第二次不调 LLM（L1 命中不重置 tokens，用调用次数判定）
        assert mock_call.call_count == 1

    @patch.object(Optimizer, "_call_llm")
    def test_style_differs_second_is_cache_miss(self, mock_call):
        mock_call.return_value = ("optimized prompt A", 100)
        o = Optimizer()
        prompt = self._unique_prompt()
        o.optimize(OptimizeRequest(prompt=prompt, platform=PlatformType.GENERIC, creative_level=7, style=None))
        o.optimize(OptimizeRequest(prompt=prompt, platform=PlatformType.GENERIC, creative_level=7, style=StyleType.REALISTIC))
        assert mock_call.call_count == 2


class TestLegacyFuzzyCompat:
    def test_fuzzy_match_prompt_still_works(self):
        from prompt_engine.models import OptimizeResult
        from prompt_engine import optimizer as opt_mod
        opt_mod._PromptCache[("a majestic cat", "midjourney", 7, 500, "", 1)] = OptimizeResult(
            optimized_prompt="a majestic cat --ar 16:9",
            platform=PlatformType.MIDJOURNEY,
            style=StyleType.REALISTIC,
            model_used="test",
            tokens_used=100,
            duration_ms=500,
        )
        matched = fuzzy_match_prompt("a majestic cat", "midjourney", 7, 500, "", 1)
        assert matched is not None
        assert matched.optimized_prompt == "a majestic cat --ar 16:9"


class TestReviewFixes:
    """评审修复回归：W2（非序列化 context）/ I6（set 归一）/ I7（空容器归一）。"""

    def test_non_serializable_context_no_raise(self):
        """评审 W2：context 含 datetime 等非 JSON 值时 make_key 不抛错，且同值 key 稳定。"""
        import datetime
        ctx = {"ts": datetime.datetime(2026, 8, 15, 10, 30)}
        key = SqlitePromptCache.make_key("a cat", "generic", 7, 500, "", 1, context=ctx)
        assert isinstance(key, str) and key.startswith("IMAGE_FMT_V1|")
        assert SqlitePromptCache.make_key("a cat", "generic", 7, 500, "", 1, context=ctx) == key

    def test_set_excluded_sorted_deterministic(self):
        """评审 I6：set 输入排序归一，同集不同迭代顺序 key 一致。"""
        k1 = SqlitePromptCache.make_key("a cat", "generic", 7, 500, "", 1, excluded_characters={"b", "a"})
        k2 = SqlitePromptCache.make_key("a cat", "generic", 7, 500, "", 1, excluded_characters={"a", "b"})
        assert k1 == k2

    def test_empty_containers_normalized(self):
        """评审 I7：空容器与 None 归一为同一 key 形态。"""
        base_args = ("a", "g", 7, 500, "", 1)
        assert SqlitePromptCache.make_key(*base_args, context={}) == SqlitePromptCache.make_key(*base_args, context=None)
        assert SqlitePromptCache.make_key(*base_args, excluded_characters=[]) == \
            SqlitePromptCache.make_key(*base_args, excluded_characters=None)
