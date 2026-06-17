"""Prompt Engine 核心库入口 — 惰性导入避免启动时 LLM 连接"""
from prompt_engine.models import (
    OptimizeRequest, OptimizeResult, PlatformType, StyleType,
    BatchOptimizeRequest, RewriteRequest,
    StyleCategory, StyleCategoryResult, AutoStyleRequest,
    FeedbackEntry, FeedbackStats,
)

__version__ = "0.21.0"


def __getattr__(name: str):
    """惰性导入：只在首次访问时才导入重量级模块。"""
    if name == "Optimizer":
        from prompt_engine.optimizer import Optimizer
        return Optimizer
    if name == "StyleCategoryClassifier":
        from prompt_engine.classifier import StyleCategoryClassifier
        return StyleCategoryClassifier
    if name == "recommend_categories_for_style":
        from prompt_engine.classifier import recommend_categories_for_style
        return recommend_categories_for_style
    if name == "FeedbackStore":
        from prompt_engine.feedback import FeedbackStore
        return FeedbackStore
    if name == "SqlitePromptCache":
        from prompt_engine.cache import SqlitePromptCache
        return SqlitePromptCache
    if name == "MemoryPromptCache":
        from prompt_engine.cache import MemoryPromptCache
        return MemoryPromptCache
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "Optimizer",
    "StyleCategoryClassifier",
    "recommend_categories_for_style",
    "FeedbackStore",
    "SqlitePromptCache",
    "MemoryPromptCache",
    "FeedbackEntry",
    "FeedbackStats",
    "OptimizeRequest",
    "BatchOptimizeRequest",
    "OptimizeResult",
    "RewriteRequest",
    "PlatformType",
    "StyleType",
    "StyleCategory",
    "StyleCategoryResult",
    "AutoStyleRequest",
]
