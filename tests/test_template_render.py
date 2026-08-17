"""显式 template 策略渲染测试。"""
import pytest

from prompt_engine.models import OptimizationStrategy, OptimizeRequest, PlatformType, StyleType


class TestTemplateRender:
    """显式 template 不走 LLM，creative_level 只控制生成强度。"""

    def get_optimizer(self):
        from prompt_engine.optimizer import Optimizer
        return Optimizer()

    def test_template_level_1_no_llm_call(self):
        """显式 template + creative_level=1 返回模板结果。"""
        opt = self.get_optimizer()
        result = opt.optimize(OptimizeRequest(
            prompt="a cat",
            platform=PlatformType.GENERIC,
            creative_level=1,
            optimization_strategy=OptimizationStrategy.TEMPLATE,
        ))
        assert result is not None
        assert result.optimized_prompt is not None
        assert len(result.optimized_prompt) > 0
        # template 路径 model_used 应为 "template"
        assert result.model_used == "template"

    def test_template_level_2_no_llm_call(self):
        """显式 template + creative_level=2 走模板直出。"""
        opt = self.get_optimizer()
        result = opt.optimize(OptimizeRequest(
            prompt="a dog",
            platform=PlatformType.MIDJOURNEY,
            creative_level=2,
            optimization_strategy=OptimizationStrategy.TEMPLATE,
        ))
        assert result is not None
        assert result.model_used == "template"
        assert len(result.optimized_prompt) > 0

    def test_template_level_3_no_llm_call(self):
        """显式 template + creative_level=3 走模板直出。"""
        opt = self.get_optimizer()
        result = opt.optimize(OptimizeRequest(
            prompt="a tree",
            platform=PlatformType.STABLE_DIFFUSION,
            creative_level=3,
            optimization_strategy=OptimizationStrategy.TEMPLATE,
        ))
        assert result is not None
        assert result.model_used == "template"

    def test_default_low_creative_level_requires_llm(self):
        """未显式 template 时，低 creative_level 不会静默改走模板。"""
        opt = self.get_optimizer()
        result = opt.optimize(OptimizeRequest(
            prompt="a cat",
            platform=PlatformType.GENERIC,
            creative_level=1,
        ))
        assert "未配置 LLM provider" in (result.error or "")
        assert result.model_used != "template"

    def test_all_platforms_have_template(self):
        """所有 7 个平台都能用模板直出"""
        opt = self.get_optimizer()
        platforms = [
            PlatformType.MIDJOURNEY,
            PlatformType.STABLE_DIFFUSION,
            PlatformType.DALLE,
            PlatformType.TONGYI,
            PlatformType.YIZHANG,
            PlatformType.JIMENG,
            PlatformType.GENERIC,
        ]
        for p in platforms:
            result = opt.optimize(OptimizeRequest(
                prompt="test",
                platform=p,
                creative_level=1,
                optimization_strategy=OptimizationStrategy.TEMPLATE,
            ))
            assert result.model_used == "template", f"Platform {p} failed template render"
            assert len(result.optimized_prompt) > 0

    def test_template_output_differs_by_creative_level(self):
        """显式模板在不同 creative_level 下输出不同。"""
        opt = self.get_optimizer()
        r1 = opt.optimize(OptimizeRequest(
            prompt="sunset", platform=PlatformType.GENERIC, creative_level=1,
            optimization_strategy=OptimizationStrategy.TEMPLATE,
        ))
        r3 = opt.optimize(OptimizeRequest(
            prompt="sunset", platform=PlatformType.GENERIC, creative_level=3,
            optimization_strategy=OptimizationStrategy.TEMPLATE,
        ))
        # 长度应不同（level 3 有更多修饰词）
        assert r1.optimized_prompt != r3.optimized_prompt

    def test_explicit_template_preserves_high_creative_level_detail(self):
        """显式模板的等级控制不能再静默压缩为 level 3。"""
        opt = self.get_optimizer()
        r3 = opt.optimize(OptimizeRequest(
            prompt="historical mountain fortress",
            platform=PlatformType.GENERIC,
            creative_level=3,
            optimization_strategy=OptimizationStrategy.TEMPLATE,
        ))
        r10 = opt.optimize(OptimizeRequest(
            prompt="historical mountain fortress",
            platform=PlatformType.GENERIC,
            creative_level=10,
            optimization_strategy=OptimizationStrategy.TEMPLATE,
        ))
        assert r10.model_used == "template"
        assert r10.optimized_prompt != r3.optimized_prompt
        assert len(r10.optimized_prompt) > len(r3.optimized_prompt)

    def test_template_render_is_deterministic(self):
        """同一请求重复执行不应因随机光影词产生不同结果。"""
        opt = self.get_optimizer()
        request = OptimizeRequest(
            prompt="historical mountain fortress",
            platform=PlatformType.GENERIC,
            creative_level=5,
            optimization_strategy=OptimizationStrategy.TEMPLATE,
        )
        first = opt.optimize(request)
        second = opt.optimize(request)
        assert first.optimized_prompt == second.optimized_prompt

    def test_tokens_zero(self):
        """模板路径 tokens=0"""
        opt = self.get_optimizer()
        result = opt.optimize(OptimizeRequest(
            prompt="flower", platform=PlatformType.GENERIC, creative_level=1,
            optimization_strategy=OptimizationStrategy.TEMPLATE,
        ))
        assert result.tokens_used == 0

    def test_duration_ms_near_zero(self):
        """模板路径耗时极短（< 100ms）"""
        opt = self.get_optimizer()
        result = opt.optimize(OptimizeRequest(
            prompt="mountain", platform=PlatformType.GENERIC, creative_level=1,
            optimization_strategy=OptimizationStrategy.TEMPLATE,
        ))
        assert result.duration_ms <= 100
