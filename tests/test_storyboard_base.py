"""Tests for StoryboardStrategy ABC and registration system"""
import pytest
from prompt_engine.storyboard.base import (
    StoryboardStrategy,
    register_storyboard,
    get_storyboard_strategy,
    list_storyboard_strategies,
    _strategies,
)


class TestRegistration:
    """注册表基本功能"""

    def setup_method(self):
        self._saved = dict(_strategies)

    def teardown_method(self):
        _strategies.clear()
        _strategies.update(self._saved)

    def test_register_decorator_registers_class(self):
        """@register_storyboard 应注册类"""
        @register_storyboard("test_strat")
        class TestStrategy(StoryboardStrategy):
            display_name = "Test"
            description = "A test strategy"
            @classmethod
            def compose(cls, concept, **options):
                return f"prompt for {concept}"

        assert "test_strat" in _strategies
        assert _strategies["test_strat"] is TestStrategy

    def test_get_storyboard_strategy_returns_class(self):
        """get_storyboard_strategy 返回已注册的类"""
        @register_storyboard("test_get")
        class TestStrategy(StoryboardStrategy):
            display_name = "Test"
            description = ""
            @classmethod
            def compose(cls, concept, **options):
                return concept

        cls = get_storyboard_strategy("test_get")
        assert cls is TestStrategy
        assert cls.compose("hello") == "hello"

    def test_get_storyboard_strategy_unknown_returns_none(self):
        """get_storyboard_strategy 对未知名称返回 None"""
        assert get_storyboard_strategy("nonexistent_strategy") is None

    def test_list_storyboard_strategies(self):
        """list_storyboard_strategies 返回格式正确的列表"""
        @register_storyboard("test_list_a")
        class StrategyA(StoryboardStrategy):
            display_name = "A"
            description = "Strategy A"
            @classmethod
            def compose(cls, concept, **options):
                return concept

        @register_storyboard("test_list_b")
        class StrategyB(StoryboardStrategy):
            display_name = "B"
            description = "Strategy B"
            @classmethod
            def compose(cls, concept, **options):
                return concept

        strategies = list_storyboard_strategies()
        names = [s["name"] for s in strategies]
        assert "test_list_a" in names
        assert "test_list_b" in names
        for s in strategies:
            assert "name" in s
            assert "display_name" in s
            assert "description" in s

    def test_duplicate_registration_overwrites(self):
        """重复注册同一名称应覆盖"""
        @register_storyboard("dup")
        class First(StoryboardStrategy):
            display_name = "First"
            description = ""
            @classmethod
            def compose(cls, concept, **options):
                return "first"

        @register_storyboard("dup")
        class Second(StoryboardStrategy):
            display_name = "Second"
            description = ""
            @classmethod
            def compose(cls, concept, **options):
                return "second"

        cls = get_storyboard_strategy("dup")
        assert cls is Second
        assert cls.compose("x") == "second"


class TestStoryboardStrategyABC:
    """ABC 强制约束"""

    def test_cannot_instantiate_abstract_class(self):
        """不能直接实例化 StoryboardStrategy"""
        with pytest.raises(TypeError):
            StoryboardStrategy()

    def test_subclass_without_compose_raises(self):
        """子类不实现 compose 时实例化报错"""
        with pytest.raises(TypeError):
            class Incomplete(StoryboardStrategy):
                pass
            Incomplete()

    def test_subclass_can_be_instantiated(self):
        """实现 compose 后可以实例化"""
        class Complete(StoryboardStrategy):
            display_name = "Complete"
            description = ""
            @classmethod
            def compose(cls, concept, **options):
                return concept

        instance = Complete()
        assert instance is not None

    def test_default_compose_batch(self):
        """compose_batch 默认实现逐场景调用 compose"""
        class BatchTest(StoryboardStrategy):
            display_name = "Batch"
            description = ""
            @classmethod
            def compose(cls, concept, **options):
                idx = options.get("scene_index", 0)
                return f"scene{idx}:{concept}"

        results = BatchTest.compose_batch(["a", "b", "c"], "full text")
        assert len(results) == 3
        assert results[0] == "scene0:a"
        assert results[1] == "scene1:b"
        assert results[2] == "scene2:c"


class TestXiaoheiIsRegistered:
    """确保 xiaohei_storyboard 策略自动注册"""

    def test_xiaohei_is_registered(self):
        """xiaohei_storyboard 策略应在模块导入后自动注册"""
        from prompt_engine.storyboard import xiaohei  # noqa: F401
        cls = get_storyboard_strategy("xiaohei_storyboard")
        assert cls is not None, "xiaohei_storyboard 策略未注册"
        assert cls.display_name == "Ian 小黑插画风"
        assert len(cls.description) > 0
