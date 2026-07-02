"""Storyboard 策略基类 + 注册表"""
from abc import ABC, abstractmethod
from typing import Any

# 故事板策略注册表
_strategies: dict[str, type["StoryboardStrategy"]] = {}


def register_storyboard(name: str):
    """装饰器：注册分镜策略"""
    def decorator(cls):
        _strategies[name] = cls
        return cls
    return decorator


def get_storyboard_strategy(name: str) -> type["StoryboardStrategy"] | None:
    """获取已注册的策略类"""
    return _strategies.get(name)


def list_storyboard_strategies() -> list[dict[str, str]]:
    """列出所有已注册的分镜策略"""
    return [
        {
            "name": name,
            "display_name": cls.display_name,
            "description": cls.description,
        }
        for name, cls in _strategies.items()
    ]


class StoryboardStrategy(ABC):
    """分镜策略基类 — 每个分镜模板风格继承此类"""

    display_name: str = ""
    description: str = ""

    @classmethod
    @abstractmethod
    def compose(cls, concept: str, **options: Any) -> str:
        """将单一场景/概念转化为生图 prompt

        Args:
            concept: 场景文字或抽象概念
            **options: 策略参数（composition_type, creative_level, style 等）

        Returns:
            优化的生图 prompt 字符串
        """
        raise NotImplementedError

    @classmethod
    def compose_batch(
        cls, scenes: list[str], full_text: str, **options: Any
    ) -> list[str]:
        """批量将场景转化为生图 prompts

        默认实现：逐场景调用 compose()。
        子类可重载以做整体优化（如保持风格一致性）。

        Args:
            scenes: 分句后的场景列表
            full_text: 原始完整文案
            **options: 策略参数

        Returns:
            生图 prompt 列表
        """
        return [
            cls.compose(scene, full_text=full_text, scene_index=i, **options)
            for i, scene in enumerate(scenes)
        ]
