"""LLM 供应商抽象基类"""
from typing import Optional
from prompt_engine.config import load_config


class BaseLLMProvider:
    """LLM 供应商基类，定义所有 provider 必须实现的接口"""

    def __init__(self, config: dict):
        self.config = config

    def chat(self, messages: list[dict]) -> tuple[str, int]:
        """调用 LLM 并返回 (响应文本, token消耗)"""
        raise NotImplementedError

    @property
    def model_name(self) -> str:
        """返回当前使用的模型名称"""
        raise NotImplementedError

    @classmethod
    def from_config(cls, config: Optional[dict] = None) -> "BaseLLMProvider":
        """工厂方法：根据配置创建 provider 实例"""
        cfg = config or load_config()
        provider_name = cfg["llm"]["provider"]
        if provider_name == "openai_compat":
            from prompt_engine.llm.openai_compat import OpenAICompatProvider
            return OpenAICompatProvider(cfg["llm"]["openai_compat"])
        elif provider_name == "xfyun":
            from prompt_engine.llm.xfyun import XfyunProvider
            return XfyunProvider(cfg["llm"]["xfyun"])
        elif provider_name == "minimax":
            from prompt_engine.llm.minimax import MiniMaxProvider
            return MiniMaxProvider(cfg["llm"]["minimax"])
        else:
            raise ValueError(f"不支持的 LLM 供应商: {provider_name}")
