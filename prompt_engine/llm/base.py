"""LLM 供应商抽象基类"""


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
    def from_llm_object(cls, llm: dict) -> "BaseLLMProvider":
        """BYOK 工厂：根据调用方传入的 llm 对象创建 provider 实例。

        llm 对象字段：provider / model / api_key / base_url(可选)。
        校验失败抛 ValueError（rest 层映射为 422 fail-closed）。
        api_key 不出现在任何日志/异常细节中。
        """
        if hasattr(llm, "model_dump"):
            llm = llm.model_dump()
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
        elif provider == "xfyun":
            cfg["base_url"] = "https://maas-coding-api.cn-huabei-1.xf-yun.com/v2"
        return provider_cls(cfg)
