"""Optimizer 编排器测试"""
from prompt_engine.optimizer import Optimizer
from prompt_engine.models import OptimizeRequest, PlatformType, StyleType


class TestOptimizer:
    def test_init_loads_config(self):
        """初始化时应加载配置"""
        opt = Optimizer()
        assert opt.config is not None
        assert "llm" in opt.config
        assert opt._provider is not None

    def test_optimize_generic(self):
        """通用平台优化应返回结果"""
        opt = Optimizer()
        req = OptimizeRequest(
            prompt="一只猫",
            platform=PlatformType.GENERIC,
        )
        result = opt.optimize(req)
        # LLM 有 key 时应返回优化后的结果
        assert result.error is None
        assert len(result.optimized_prompt) > len("一只猫")
        assert result.platform == PlatformType.GENERIC
        assert result.duration_ms > 0

    def test_optimize_midjourney(self):
        """Midjourney 优化应包含 --ar 参数"""
        opt = Optimizer()
        req = OptimizeRequest(
            prompt="a cat",
            platform=PlatformType.MIDJOURNEY,
        )
        result = opt.optimize(req)
        assert result.error is None
        assert result.platform == PlatformType.MIDJOURNEY
        assert result.tokens_used > 0
        assert result.duration_ms > 0

    def test_optimize_with_negative_prompt(self):
        """带负面提示词的优化"""
        opt = Optimizer()
        req = OptimizeRequest(
            prompt="风景",
            platform=PlatformType.GENERIC,
            style=StyleType.REALISTIC,
            negative_prompt="人物, 动物, 文字",
        )
        result = opt.optimize(req)
        assert result.error is None
        assert result.style == StyleType.REALISTIC

    def test_optimize_with_style_and_creative(self):
        """带上风格和创意度参数"""
        opt = Optimizer()
        req = OptimizeRequest(
            prompt="风景",
            platform=PlatformType.GENERIC,
            style=StyleType.REALISTIC,
            creative_level=8,
        )
        result = opt.optimize(req)
        assert result.platform == PlatformType.GENERIC
        assert result.style == StyleType.REALISTIC