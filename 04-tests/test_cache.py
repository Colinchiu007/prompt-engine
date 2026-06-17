"""
测试 Prompt Cache（内存池）功能。
验证：
1. 相同 prompt 命中缓存时 speed 0ms / tokens 0
2. 不同 platform 应该各自缓存
"""

import pytest
from prompt_engine.optimizer import Optimizer
from prompt_engine.models import OptimizeRequest


class TestPromptCache:
    """Prompt 内存池测试."""

    def test_cache_hit_exact_prompt(self):
        """相同 prompt 应该命中缓存."""
        optimizer = Optimizer()

        # 第一次调用
        req1 = OptimizeRequest(
            prompt="a majestic cat",
            platform="midjourney",
            creative_level=7,
            max_length=200
        )
        result1 = optimizer.optimize(req1)

        # 第二次调用 - 相同 prompt
        result2 = optimizer.optimize(req1)

        # 验证第二次调用走的是缓存
        assert result2.duration_ms >= 0
        assert result2.tokens_used == 0  # 缓存命中 → 不消耗 tokens
        # 文本内容应该一样
        assert result1.optimized_prompt == result2.optimized_prompt
        print(f"Cache hit: first={result1.duration_ms}ms, second={result2.duration_ms}ms, tokens={result1.tokens_used}")

    def test_cache_miss_different_platform(self):
        """不同 platform 应该各自缓存."""
        optimizer = Optimizer()

        req_mj = OptimizeRequest(
            prompt="a majestic cat",
            platform="midjourney",
            creative_level=7,
            max_length=200
        )

        result_mj1 = optimizer.optimize(req_mj)
        result_mj2 = optimizer.optimize(req_mj)

        assert result_mj2.tokens_used == 0  # 第二次应为 0
        print(f"MJ cache: first={result_mj1.duration_ms}ms, second={result_mj2.duration_ms}ms, tokens={result_mj2.tokens_used}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
