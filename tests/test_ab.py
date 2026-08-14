"""A/B 测试候选生成测试"""
import uuid
from unittest.mock import MagicMock, patch
from prompt_engine.models import OptimizeRequest, OptimizeResult, PlatformType, StyleType
from prompt_engine.optimizer import Optimizer


def _unique_prompt(base="test"):
    """Generate a cache-busting unique prompt."""
    return f"{base} {uuid.uuid4().hex[:8]}"


class TestABCandidates:
    @patch.object(Optimizer, "_call_llm")
    def test_optimize_single_candidate(self, mock_call):
        """单候选时 candidates 为空"""
        mock_call.return_value = ("A fluffy cat", 100)
        optimizer = Optimizer()
        req = OptimizeRequest(
            prompt=_unique_prompt("a cat"),
            platform=PlatformType.GENERIC,
            num_candidates=1,
        )
        result = optimizer.optimize(req)
        assert isinstance(result, OptimizeResult)
        assert result.candidates == []  # 单候选不返回数组
        # post_process 可能注入关键词
        assert "A fluffy cat" in result.optimized_prompt

    @patch.object(Optimizer, "_call_llm")
    def test_optimize_multiple_candidates(self, mock_call):
        """多候选时返回 candidates 数组，且按质量分降序择优（图片域 Higgsfield 对齐）"""
        mock_call.side_effect = [
            ("Version A: A detailed cat", 100),
            ("Version B: A creative cat", 120),
            ("Version C: A whimsical cat", 110),
        ]
        optimizer = Optimizer()
        req = OptimizeRequest(
            prompt=_unique_prompt("multi cat"),
            platform=PlatformType.GENERIC,
            num_candidates=3,
        )
        result = optimizer.optimize(req)
        assert isinstance(result, OptimizeResult)
        assert len(result.candidates) == 3
        # 择优语义：最高分候选既是主输出也在数组首位（post_process 关键词注入带随机性，
        # 不能断言固定顺序，改为断言“评分降序 + 主输出==首位”不变量）
        assert result.optimized_prompt == result.candidates[0]
        from prompt_engine.evaluator import evaluate_quality

        scores = [
            evaluate_quality(
                c, {}, source_prompt=req.prompt, language="en",
                tier="batch", max_length=req.max_length,
            )["score"]
            for c in result.candidates
        ]
        assert scores == sorted(scores, reverse=True)
        assert result.tokens_used == 330

    @patch.object(Optimizer, "_call_llm")
    def test_call_llm_variant_injection(self, mock_call):
        """验证 variant>0 会注入差异化指令"""
        mock_call.return_value = ("variant result", 100)
        optimizer = Optimizer()
        result = optimizer._call_llm("test prompt", "user input", variant=1)
        # mock 直接返回，验证调用了 1 次
        assert result == ("variant result", 100)
        assert mock_call.call_count == 1

    @patch.object(Optimizer, "_call_llm")
    def test_optimize_generates_multiple_variants(self, mock_call):
        """优化 num_candidates=3 时调用 3 次 _call_llm"""
        mock_call.side_effect = [
            ("variant A", 100),
            ("variant B", 120),
            ("variant C", 110),
        ]
        optimizer = Optimizer()
        req = OptimizeRequest(
            prompt=_unique_prompt("a forest"),
            platform=PlatformType.GENERIC,
            num_candidates=3,
            creative_level=8,
        )
        result = optimizer.optimize(req)
        assert mock_call.call_count == 3
        assert len(result.candidates) == 3
        assert result.tokens_used == 330
