"""Storyboard 策略模块 — 可插拔的分镜模板策略"""
from prompt_engine.storyboard.base import (
    StoryboardStrategy,
    register_storyboard,
    get_storyboard_strategy,
    list_storyboard_strategies,
)

# 导入使 @register_storyboard 装饰器生效
from prompt_engine.storyboard import xiaohei  # noqa: F401

__all__ = [
    "StoryboardStrategy",
    "register_storyboard",
    "get_storyboard_strategy",
    "list_storyboard_strategies",
]
