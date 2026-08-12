"""视频平台策略注册表（独立实现，机制复刻图片引擎 BaseStrategy 注册体系）。"""
from video_prompt_engine.strategies.base import BaseVideoStrategy, get_strategy, list_strategies, register

# 显式导入使 @register 生效
from video_prompt_engine.strategies import generic_video  # noqa: F401
from video_prompt_engine.strategies import seedance       # noqa: F401

__all__ = ["BaseVideoStrategy", "register", "get_strategy", "list_strategies"]
