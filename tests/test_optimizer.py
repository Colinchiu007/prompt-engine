"""Optimizer 编排器测试"""
import uuid
from unittest.mock import patch
from prompt_engine.optimizer import Optimizer
from prompt_engine.models import OptimizeRequest, PlatformType, StyleType


def _unique_prompt(base="test"):
    """Generate a cache-busting unique prompt."""
    return f"{base} {uuid.uuid4().hex[:8]}"


class TestOptimizer:
    def test_init_loads_config(self):
        optimizer = Optimizer()
        assert optimizer.config is not None

    @patch.object(Optimizer, "_call_llm")
    def test_optimize_generic(self, mock_call):
        mock_call.return_value = ("optimized prompt", 100)
        optimizer = Optimizer()
        req = OptimizeRequest(prompt=_unique_prompt(), platform=PlatformType.GENERIC)
        result = optimizer.optimize(req)
        # post_process 可能注入 MJ 关键词
        assert "optimized prompt" in result.optimized_prompt
        assert result.tokens_used == 100

    @patch.object(Optimizer, "_call_llm")
    def test_optimize_midjourney(self, mock_call):
        mock_call.return_value = ("MJ prompt with --ar 16:9", 120)
        optimizer = Optimizer()
        req = OptimizeRequest(prompt=_unique_prompt("mj"), platform=PlatformType.MIDJOURNEY)
        result = optimizer.optimize(req)
        assert "MJ" in result.optimized_prompt
        assert result.tokens_used == 120

    @patch.object(Optimizer, "_call_llm")
    def test_optimize_with_negative_prompt(self, mock_call):
        mock_call.return_value = ("prompt without dogs or cats", 130)
        optimizer = Optimizer()
        req = OptimizeRequest(
            prompt=_unique_prompt("a park"),
            platform=PlatformType.GENERIC,
            negative_prompt="dogs, cats, people",
        )
        result = optimizer.optimize(req)
        assert "without dogs or cats" in result.optimized_prompt

    @patch.object(Optimizer, "_call_llm")
    def test_optimize_with_style_and_creative(self, mock_call):
        mock_call.return_value = ("oil painting style", 150)
        optimizer = Optimizer()
        req = OptimizeRequest(
            prompt=_unique_prompt("mountain"),
            platform=PlatformType.GENERIC,
            style=StyleType.OIL_PAINTING,
            creative_level=9,
        )
        result = optimizer.optimize(req)
        assert "oil painting" in result.optimized_prompt
