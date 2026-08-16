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
        if provider_name in ("openai_compat", "ai_router"):
            from prompt_engine.llm.openai_compat import OpenAICompatProvider
            return OpenAICompatProvider(cfg["llm"][provider_name])
        elif provider_name == "xfyun":
            from prompt_engine.llm.xfyun import XfyunProvider
            return XfyunProvider(cfg["llm"]["xfyun"])
        elif provider_name == "gemini":
            from prompt_engine.llm.gemini import GeminiProvider
            return GeminiProvider(cfg["llm"]["gemini"])
        elif provider_name == "minimax":
            from prompt_engine.llm.minimax import MiniMaxProvider
            return MiniMaxProvider(cfg["llm"]["minimax"])
        elif provider_name == "deepseek":
            from prompt_engine.llm.deepseek import DeepSeekProvider
            return DeepSeekProvider(cfg["llm"]["deepseek"])
        else:
            raise ValueError(f"不支持的 LLM 供应商: {provider_name}")

    @classmethod
    def from_llm_object(cls, llm: dict) -> "BaseLLMProvider":
        """BYOK 工厂：根据调用方传入的 llm 对象创建 provider 实例。

        llm 对象字段：provider / model / api_key / base_url(可选)。
        校验失败抛 ValueError（rest 层映射为 422 fail-closed）。
        api_key 不出现在任何日志/异常细节中。
        """
        if not isinstance(llm, dict):
            raise ValueError("llm 必须是对象 { provider, model, api_key, base_url? }")
        provider = str(llm.get("provider") or "").strip()
        api_key = str(llm.get("api_key") or "").strip()
        model = str(llm.get("model") or "").strip()
        base_url = str(llm.get("base_url") or "").strip() or None
        if not provider:
            raise ValueError("llm.provider 必填")
        if not api_key:
            raise ValueError(f"llm.api_key 必填（provider={provider}）")
        if not model:
            raise ValueError(f"llm.model 必填（provider={provider}）")

        if provider in ("openai_compat", "ai_router", "sensenova"):
            from prompt_engine.llm.openai_compat import OpenAICompatProvider
            cfg = {"api_key": api_key, "model": model}
            if base_url:
                cfg["base_url"] = base_url
            elif provider == "sensenova":
                cfg["base_url"] = "https://token.sensenova.cn/v1"
            else:
                cfg["base_url"] = "https://api.openai.com/v1"
            return OpenAICompatProvider(cfg)

        from prompt_engine.llm import _PROVIDERS
        provider_cls = _PROVIDERS.get(provider)
        if provider_cls is None:
            raise ValueError(f"不支持的 LLM 供应商: {provider}（可用: {sorted(_PROVIDERS)}）")
        cfg: dict = {"api_key": api_key, "model": model}
        if base_url:
            cfg["base_url"] = base_url
        return provider_cls(cfg)
