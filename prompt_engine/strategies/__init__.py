"""Strategies — 平台策略注册表（自动注册所有策略）"""
from prompt_engine.strategies.base import BaseStrategy, register, get_strategy, list_strategies

# 显式导入使 @register 装饰器生效
from prompt_engine.strategies import midjourney       # noqa: F401
from prompt_engine.strategies import stable_diffusion  # noqa: F401
from prompt_engine.strategies import dalle             # noqa: F401
from prompt_engine.strategies import tongyi            # noqa: F401
from prompt_engine.strategies import yizhang           # noqa: F401
from prompt_engine.strategies import jimeng            # noqa: F401
from prompt_engine.strategies import generic           # noqa: F401
from prompt_engine.strategies import xiaohei_storyboard  # noqa: F401

__all__ = ["BaseStrategy", "register", "get_strategy", "list_strategies"]