"""v0.19.0 F2 — 低创意模板直出测试"""
import pytest

from prompt_engine.models import OptimizeRequest, PlatformType, StyleType


class TestTemplateRender:
    """低创意度（1-3）不走 LLM，模板直出"""

    def get_optimizer(self):
        from prompt_engine.optimizer import Optimizer
        return Optimizer()

    def test_crative_level_1_no_llm_call(self):
        """creative_level=1 返回结果且 model_used=template"""
        opt = self.get_optimizer()
        result = opt.optimize(OptimizeRequest(
            prompt="a cat",
            platform=PlatformType.GENERIC,
            creative_level=1,
        ))
        assert result is not None
        assert result.optimized_prompt is not None
        assert len(result.optimized_prompt) > 0
        # template 路径 model_used 应为 "template"
        assert result.model_used == "template"

    def test_creative_level_2_no_llm_call(self):
        """creative_level=2 也走模板直出"""
        opt = self.get_optimizer()
        result = opt.optimize(OptimizeRequest(
            prompt="a dog",
            platform=PlatformType.MIDJOURNEY,
            creative_level=2,
        ))
        assert result is not None
        assert result.model_used == "template"
        assert len(result.optimized_prompt) > 0

    def test_creative_level_3_no_llm_call(self):
        """creative_level=3 也走模板直出"""
        opt = self.get_optimizer()
        result = opt.optimize(OptimizeRequest(
            prompt="a tree",
            platform=PlatformType.STABLE_DIFFUSION,
            creative_level=3,
        ))
        assert result is not None
        assert result.model_used == "template"

    def test_creative_level_4_still_uses_llm(self):
        """creative_level>=4 不走模板，model_used 不是 template"""
        opt = self.get_optimizer()
        result = opt.optimize(OptimizeRequest(
            prompt="a cat",
            platform=PlatformType.GENERIC,
            creative_level=4,
        ))
        # creative_level >=4 走 LLM，model_used 不会是 "template"
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
            ))
            assert result.model_used == "template", f"Platform {p} failed template render"
            assert len(result.optimized_prompt) > 0

    def test_template_output_differs_by_creative_level(self):
        """不同 creative_level 的模板输出应不同（1 vs 3 质量词不同）"""
        opt = self.get_optimizer()
        r1 = opt.optimize(OptimizeRequest(
            prompt="sunset", platform=PlatformType.GENERIC, creative_level=1,
        ))
        r3 = opt.optimize(OptimizeRequest(
            prompt="sunset", platform=PlatformType.GENERIC, creative_level=3,
        ))
        # 长度应不同（level 3 有更多修饰词）
        assert r1.optimized_prompt != r3.optimized_prompt

    def test_tokens_zero(self):
        """模板路径 tokens=0"""
        opt = self.get_optimizer()
        result = opt.optimize(OptimizeRequest(
            prompt="flower", platform=PlatformType.GENERIC, creative_level=1,
        ))
        assert result.tokens_used == 0

    def test_duration_ms_near_zero(self):
        """模板路径耗时极短（< 100ms）"""
        opt = self.get_optimizer()
        result = opt.optimize(OptimizeRequest(
            prompt="mountain", platform=PlatformType.GENERIC, creative_level=1,
        ))
        assert result.duration_ms <= 100
