"""平台策略基类 + 注册表"""
from typing import Optional
from prompt_engine.models import PlatformType, StyleType

# 策略注册表
_strategies: dict[str, type["BaseStrategy"]] = {}


def register(platform: str):
    """装饰器：注册平台策略"""
    def decorator(cls):
        _strategies[platform] = cls
        return cls
    return decorator


def get_strategy(platform: str) -> Optional[type["BaseStrategy"]]:
    """获取已注册的策略类"""
    return _strategies.get(platform)


def list_strategies() -> list[str]:
    """列出所有已注册的平台"""
    return list(_strategies.keys())


class BaseStrategy:
    """策略基类 — 每个平台继承此类"""

    platform: PlatformType = PlatformType.GENERIC

    @classmethod
    def build_system_prompt(
        cls,
        style: Optional[StyleType] = None,
        creative_level: int = 5,
        max_length: int = 500,
    ) -> str:
        """构建系统提示词，指导 LLM 按照平台规则输出"""
        raise NotImplementedError

    @classmethod
    def post_process(cls, raw_output: str) -> str:
        """后处理：清理、格式化 LLM 原始输出"""
        return raw_output.strip().strip('"').strip("'")