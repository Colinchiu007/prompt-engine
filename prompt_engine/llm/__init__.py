"""LLM 供应商工厂 — 统一注册和管理"""
from prompt_engine.llm.base import BaseLLMProvider

# 供应商注册表
_PROVIDERS: dict[str, type[BaseLLMProvider]] = {}


def register(name: str):
    """装饰器：注册 LLM 供应商。"""
    def wrapper(cls):
        _PROVIDERS[name] = cls
        return cls
    return wrapper


def list_providers() -> list[str]:
    """列出所有已注册的供应商名称。"""
    return list(_PROVIDERS.keys())


def create_provider(name: str, **kwargs) -> BaseLLMProvider:
    """创建指定供应商的实例。"""
    if name not in _PROVIDERS:
        raise ValueError(f"Unknown provider: {name}. Available: {list(_PROVIDERS.keys())}")
    return _PROVIDERS[name](**kwargs)


# 导入并注册各供应商
from prompt_engine.llm.openai_compat import OpenAICompatProvider
_PROVIDERS["openai_compat"] = OpenAICompatProvider

from prompt_engine.llm.xfyun import XfyunProvider
_PROVIDERS["xfyun"] = XfyunProvider

try:
    from prompt_engine.llm.gemini import GeminiProvider
    _PROVIDERS["gemini"] = GeminiProvider
except ImportError:
    pass

from prompt_engine.llm.minimax import MiniMaxProvider
_PROVIDERS["minimax"] = MiniMaxProvider

from prompt_engine.llm.deepseek import DeepSeekProvider
_PROVIDERS["deepseek"] = DeepSeekProvider

__all__ = ["BaseLLMProvider", "list_providers", "create_provider", "register"]
