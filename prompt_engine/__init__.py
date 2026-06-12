"""Prompt Engine 核心库入口 — 惰性导入避免启动时 LLM 连接"""
from prompt_engine.models import (
    OptimizeRequest, OptimizeResult, PlatformType, StyleType,
    BatchOptimizeRequest, RewriteRequest,
    StyleCategory, StyleCategoryResult, AutoStyleRequest,
)

__version__ = "0.4.0"


def __getattr__(name: str):
    """惰性导入：只在首次访问时才导入 Optimizer 和 StyleCategoryClassifier。"""
    if name == "Optimizer":
        from prompt_engine.optimizer import Optimizer
        return Optimizer
    if name == "StyleCategoryClassifier":
        from prompt_engine.classifier import StyleCategoryClassifier
        return StyleCategoryClassifier
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "Optimizer",
    "StyleCategoryClassifier",
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