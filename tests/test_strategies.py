"""平台策略测试"""
from prompt_engine.strategies import get_strategy, list_strategies
from prompt_engine.strategies.base import register
from prompt_engine.models import PlatformType


class TestStrategyRegistry:
    def test_list_strategies(self):
        strategies = list_strategies()
        assert "midjourney" in strategies
        assert "stable_diffusion" in strategies
        assert "dalle" in strategies
        assert "tongyi" in strategies
        assert "yizhang" in strategies
        assert "jimeng" in strategies
        assert "generic" in strategies
        assert len(strategies) == 7

    def test_get_midjourney(self):
        cls = get_strategy("midjourney")
        assert cls is not None
        assert cls.platform == PlatformType.MIDJOURNEY

    def test_get_generic(self):
        cls = get_strategy("generic")
        assert cls is not None
        assert cls.platform == PlatformType.GENERIC

    def test_get_unknown(self):
        cls = get_strategy("nonexistent_platform")
        assert cls is None

    def test_register_decorator(self):
        """验证注册装饰器正常工作"""
        @register("test_platform")
        class TestStrategy:
            platform = PlatformType.GENERIC
        assert get_strategy("test_platform") == TestStrategy
        # 清理
        from prompt_engine.strategies.base import _strategies
        _strategies.pop("test_platform", None)


class TestMidjourneyStrategy:
    def test_build_system_prompt_contains_mj_params(self):
        from prompt_engine.strategies.midjourney import MidjourneyStrategy
        prompt = MidjourneyStrategy.build_system_prompt()
        assert "--ar" in prompt
        assert "--v 6" in prompt
        assert "--s" in prompt or "stylize" in prompt

    def test_build_system_prompt_with_style(self):
        from prompt_engine.strategies.midjourney import MidjourneyStrategy
        from prompt_engine.models import StyleType
        prompt = MidjourneyStrategy.build_system_prompt(style=StyleType.REALISTIC)
        assert "写实" in prompt or "realistic" in prompt.lower()


class TestStableDiffusionStrategy:
    def test_build_system_prompt_contains_weight_syntax(self):
        from prompt_engine.strategies.stable_diffusion import StableDiffusionStrategy
        prompt = StableDiffusionStrategy.build_system_prompt()
        assert "(" in prompt or "weight" in prompt
        assert "masterpiece" in prompt.lower() or "quality" in prompt.lower()

    def test_post_process_strips_quotes(self):
        from prompt_engine.strategies.stable_diffusion import StableDiffusionStrategy
        result = StableDiffusionStrategy.post_process('"a beautiful cat"')
        # 引号被移除，关键词被注入追加
        assert '"' not in result.split(",")[0], f"Quotes not stripped: {result}"
        assert "a beautiful cat" in result


class TestDalleStrategy:
    def test_build_system_prompt_natural_language(self):
        from prompt_engine.strategies.dalle import DalleStrategy
        prompt = DalleStrategy.build_system_prompt()
        assert "自然语言" in prompt or "natural" in prompt.lower()


class TestTongyiStrategy:
    def test_build_system_prompt_chinese(self):
        from prompt_engine.strategies.tongyi import TongyiStrategy
        prompt = TongyiStrategy.build_system_prompt()
        assert "中文" in prompt or "通义" in prompt


class TestYizhangStrategy:
    def test_build_system_prompt_chinese(self):
        from prompt_engine.strategies.yizhang import YizhangStrategy
        prompt = YizhangStrategy.build_system_prompt()
        assert "中文" in prompt or "文心" in prompt or "一格" in prompt


class TestJimengStrategy:
    def test_build_system_prompt_chinese(self):
        from prompt_engine.strategies.jimeng import JimengStrategy
        prompt = JimengStrategy.build_system_prompt()
        assert "中文" in prompt or "即梦" in prompt


class TestGenericStrategy:
    def test_build_system_prompt_generic(self):
        from prompt_engine.strategies.generic import GenericStrategy
        prompt = GenericStrategy.build_system_prompt()
        assert "expert prompt engineer" in prompt
        assert "platform-agnostic" in prompt

    def test_build_system_prompt_creative_level(self):
        from prompt_engine.strategies.generic import GenericStrategy
        prompt = GenericStrategy.build_system_prompt(creative_level=8)
        assert "8" in prompt


class TestBaseStrategyPostProcess:
    def test_strip_quotes(self):
        from prompt_engine.strategies import generic
        raw = generic.GenericStrategy.post_process('"hello"')
        assert '"' not in raw.split(",")[0], f"Quotes not stripped: {raw}"
        assert "hello" in raw
        raw2 = generic.GenericStrategy.post_process("'hello'")
        assert "'" not in raw2.split(",")[0], f"Quotes not stripped: {raw2}"
        assert "hello" in raw2

    def test_strip_whitespace(self):
        from prompt_engine.strategies import generic
        raw = generic.GenericStrategy.post_process("  hello  ")
        # 空格被移除，关键词被注入追加
        assert not raw.startswith("  "), f"Leading space not stripped: {raw}"
        assert "hello" in raw