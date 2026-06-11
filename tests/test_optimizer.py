"""Optimizer 编排器测试"""
from unittest.mock import patch, MagicMock
from prompt_engine.optimizer import Optimizer
from prompt_engine.models import OptimizeRequest, PlatformType, StyleType


class TestOptimizer:
    def test_init_loads_config(self):
        """初始化时应加载配置"""
        opt = Optimizer()
        assert opt.config is not None
        assert "llm" in opt.config
        assert opt._provider is not None

    def test_optimize_generic_fallback(self):
        """不存在的平台应回退到 generic"""
        opt = Optimizer()
        req = OptimizeRequest(
            prompt="一只猫",
            platform=PlatformType.GENERIC,
        )
        result = opt.optimize(req)
        # LLM 未配置真实 key，应返回降级结果
        assert result.error is not None
        assert result.optimized_prompt == "一只猫"

    def test_optimize_midjourney_fallback(self):
        """Midjourney 平台，LLM 无 key 时应降级"""
        opt = Optimizer()
        req = OptimizeRequest(
            prompt="a cat",
            platform=PlatformType.MIDJOURNEY,
        )
        result = opt.optimize(req)
        assert result.error is not None
        # 降级时返回原 prompt
        assert result.optimized_prompt == "a cat"

    def test_optimize_with_style(self):
        """带上风格参数"""
        opt = Optimizer()
        req = OptimizeRequest(
            prompt="风景",
            platform=PlatformType.GENERIC,
            style=StyleType.REALISTIC,
        )
        result = opt.optimize(req)
        assert result.platform == PlatformType.GENERIC
        assert result.style == StyleType.REALISTIC