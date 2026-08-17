"""视频引擎 LLM 供应商 — 复用共享内核传输层（prompt_engine_core.llm）。

支持调用方请求中的 OpenAI 兼容 BYOK 绑定；视频引擎自身不读取文字 LLM 配置。
"""
from __future__ import annotations

from typing import Any

from prompt_engine_core.llm import BaseLLMProvider


class BaseVideoLLMProvider(BaseLLMProvider):
    """OpenAI 兼容 chat completions 调用（继承共享内核：超时/动态 max_tokens/16384 cap）。"""

    _DEFAULT_BASE_URLS = {
        "openai_compat": "https://api.openai.com/v1",
        "ai_router": "https://api.openai.com/v1",
        "sensenova": "https://token.sensenova.cn/v1",
        "deepseek": "https://api.deepseek.com/v1",
        "minimax": "https://api.minimaxi.com/v1",
    }

    @classmethod
    def from_llm_object(cls, llm: Any) -> "BaseVideoLLMProvider":
        """从调用方 LLM 对象创建请求级 provider，不读取 config/env Key。"""
        if hasattr(llm, "model_dump"):
            llm = llm.model_dump()
        if not isinstance(llm, dict):
            raise ValueError("llm 必须是对象 { provider, model, api_key, base_url? }")

        provider = str(llm.get("provider") or "").strip().lower()
        model = str(llm.get("model") or "").strip()
        api_key = str(llm.get("api_key") or "").strip()
        base_url = str(llm.get("base_url") or "").strip() or None
        if not provider:
            raise ValueError("llm.provider 必填")
        if not model:
            raise ValueError("llm.model 必填")
        if not api_key:
            raise ValueError("llm.api_key 必填")
        if provider not in cls._DEFAULT_BASE_URLS:
            raise ValueError(f"不支持的视频 LLM 供应商: {provider}")

        config = {
            "llm": {
                "provider": provider,
                "model": model,
                "api_key": api_key,
                "base_url": base_url or cls._DEFAULT_BASE_URLS[provider],
            }
        }
        return cls(config)

    def call(
        self, system_prompt: str, user_prompt: str, variant: int = 0, max_length: int | None = None,
    ) -> tuple[str, int]:
        """返回 (content, tokens)。无 key 时抛错（fail closed）。

        C2：max_tokens 按 max_length 动态放大（refined 长模板 ≤40000 字符）；
        W1：默认 cap 16384（gpt-4o 级常见输出上限），防 le=40000 时 max_tokens=80000
        被 OpenAI 兼容端点 400 拒绝；需更大输出时配置 llm.max_tokens_cap。
        """
        # 刻意先于 super().call() 检查，确保任何缺 Key 请求都 fail closed。
        if not self.api_key:
            raise RuntimeError("调用方 LLM API Key 未配置")
        return super().call(system_prompt, user_prompt, variant=variant, max_length=max_length)


__all__ = ["BaseVideoLLMProvider"]
