"""策略注册器 — 跨引擎共享的 @register/get_strategy/list_strategies 机械件。

来源：图片/视频引擎 strategies/base.py 各自的 _REGISTRY 复制实现，泛化为通用注册器。
"""
from __future__ import annotations

from typing import Callable, Generic, TypeVar

T = TypeVar("T")


class StrategyRegistry(Generic[T]):
    """泛型策略注册表：平台名（小写）→ 策略类。"""

    def __init__(self):
        self._registry: dict[str, T] = {}

    def register(self, platform: str) -> Callable[[T], T]:
        """注册装饰器。"""
        def decorator(cls: T) -> T:
            self._registry[str(platform or "").lower()] = cls
            return cls
        return decorator

    def get(self, platform: str) -> T | None:
        return self._registry.get(str(platform or "").lower())

    def list(self) -> list[str]:
        return sorted(self._registry.keys())

    def items(self) -> list[tuple[str, T]]:
        """按注册（插入）顺序返回 (key, value) 列表。"""
        return list(self._registry.items())

    def __contains__(self, platform: str) -> bool:
        return str(platform or "").lower() in self._registry
