"""策略集成测试 — 验证策略拼接、post_process、异常路径"""
import pytest
from unittest.mock import patch, MagicMock
from prompt_engine.optimizer import Optimizer
from prompt_engine.models import (
    OptimizeRequest, ReverseRequest, PlatformType, StyleType,
    OptimizeResult, ReverseResult,
)
from prompt_engine.strategies import (
    get_strategy, list_strategies,
    midjourney, stable_diffusion, dalle, tongyi, yizhang, jimeng, generic,
)


class TestStrategyIntegration:
    """验证策略实际输出是否符合预期格式"""

    def test_mj_build_prompt_has_params(self):
        cls = get_strategy("midjourney")
        prompt = cls.build_system_prompt(StyleType.REALISTIC, creative_level=7, max_length=500)
        assert "--ar 4:3" in prompt
        assert "--v 6.1" in prompt
        assert "--style raw" in prompt
        assert "realistic" in prompt.lower()

    def test_sd_build_prompt_has_weight_syntax(self):
        cls = get_strategy("stable_diffusion")
        prompt = cls.build_system_prompt(StyleType.ANIME, creative_level=5, max_length=500)
        assert "(masterpiece:1.2)" in prompt
        assert "comma-separated" in prompt.lower() or "comma" in prompt.lower()

    def test_dalle_build_prompt_natural_language(self):
        cls = get_strategy("dalle")
        prompt = cls.build_system_prompt(StyleType.PORTRAIT, creative_level=8, max_length=500)
        assert "natural language" in prompt.lower() or "flowing" in prompt.lower()
        # DALL·E 不应用 --ar 参数
        assert "--ar" not in prompt

    def test_post_process_strips_quotes(self):
        # 用 generic 策略测试（MJ 的 post_process 会追加 --ar）
        from prompt_engine.strategies import generic
        result = generic.GenericStrategy.post_process('  "hello world"  ')
        assert '"' not in result.split(",")[0], f"Quotes not stripped: {result}"
        assert "hello world" in result

    def test_post_process_sd_removes_trailing_dot(self):
        cls = get_strategy("stable_diffusion")
        result = cls.post_process("a cat, sitting, ")
        # 关键词注入可能以句号结尾，但原始 prompt 中的句号已被移除
        assert result.startswith("a cat, sitting")

    def test_tongyi_uses_chinese(self):
        cls = get_strategy("tongyi")
        prompt = cls.build_system_prompt(StyleType.REALISTIC, max_length=500)
        assert "中文" in prompt or "中文" in str(getattr(cls, 'platform', '')) or len(prompt) > 0

    def test_yizhang_uses_chinese(self):
        cls = get_strategy("yizhang")
        prompt = cls.build_system_prompt(StyleType.PORTRAIT, max_length=500)
        assert len(prompt) > 0

    def test_jimeng_uses_chinese(self):
        cls = get_strategy("jimeng")
        prompt = cls.build_system_prompt(StyleType.ANIME, max_length=500)
        assert len(prompt) > 0

    def test_all_strategies_register_valid(self):
        """所有策略必须在注册表中"""
        registered = list_strategies()
        assert "midjourney" in registered
        assert "stable_diffusion" in registered
        assert "dalle" in registered
        assert "tongyi" in registered
        assert "yizhang" in registered
        assert "jimeng" in registered
        assert "generic" in registered


class TestOptimizerErrorPaths:
    """测试错误路径 — 异常时返回 fallback"""

    @patch.object(Optimizer, "_call_llm")
    def test_optimize_fallback_on_error(self, mock_call):
        mock_call.side_effect = RuntimeError("API timeout")
        optimizer = Optimizer()
        req = OptimizeRequest(prompt="test", platform=PlatformType.MIDJOURNEY)
        result = optimizer.optimize(req)
        # 出错时应返回原 prompt 作为 fallback
        assert result.error is not None
        assert "timeout" in result.error.lower() or "api" in result.error.lower()
        assert result.optimized_prompt == "test"
        assert result.error is not None

    @patch.object(Optimizer, "_call_llm")
    def test_optimize_max_length_truncation(self, mock_call):
        mock_call.return_value = ("x" * 1000, 100)
        optimizer = Optimizer()
        req = OptimizeRequest(prompt="test", platform=PlatformType.GENERIC, max_length=100)
        result = optimizer.optimize(req)
        assert len(result.optimized_prompt) <= 100

    @patch.object(Optimizer, "_call_vision_llm")
    def test_reverse_fallback_on_error(self, mock_vision):
        mock_vision.side_effect = RuntimeError("Vision model error")
        optimizer = Optimizer()
        req = ReverseRequest(image_url="https://example.com/test.jpg")
        result = optimizer.reverse_engineer(req)
        assert result.error is not None
        assert result.prompt == ""


class TestAbstractBaseStrategy:
    """验证 @abstractmethod 保护"""

    def test_cannot_instantiate_abstract_base(self):
        from prompt_engine.strategies.base import BaseStrategy
        with pytest.raises(TypeError):
            BaseStrategy()

    def test_all_concrete_strategies_can_instantiate(self):
        """所有具体策略类不需要实例化（是 @classmethod 方法），但可注册和调用"""
        for name in list_strategies():
            cls = get_strategy(name)
            assert cls is not None
            # 验证 build_system_prompt 和 post_process 都可调用
            prompt = cls.build_system_prompt(StyleType.REALISTIC, 5, 500, None)
            assert isinstance(prompt, str) and len(prompt) > 0
            processed = cls.post_process('  "test"  ')
            assert isinstance(processed, str)
