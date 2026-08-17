"""视频引擎 LLM 供应商 — 复用共享内核传输层（prompt_engine_core.llm）。

支持 openai_compat/minimax/gemini 语义；超时、动态 max_tokens 与 16384 默认 cap
由 core.BaseLLMProvider 承载，本类仅保留视频引擎专属错误消息（VIDEO_LLM_API_KEY）。
"""
from __future__ import annotations

from prompt_engine_core.llm import BaseLLMProvider


class BaseVideoLLMProvider(BaseLLMProvider):
    """OpenAI 兼容 chat completions 调用（继承共享内核：超时/动态 max_tokens/16384 cap）。"""

    def call(
        self, system_prompt: str, user_prompt: str, variant: int = 0, max_length: int | None = None,
    ) -> tuple[str, int]:
        """返回 (content, tokens)。无 key 时抛错（fail closed）。

        C2：max_tokens 按 max_length 动态放大（refined 长模板 ≤40000 字符）；
        W1：默认 cap 16384（gpt-4o 级常见输出上限），防 le=40000 时 max_tokens=80000
        被 OpenAI 兼容端点 400 拒绝；需更大输出时配置 llm.max_tokens_cap。
        """
        # 刻意先于 super().call() 检查：core 的报错文案不含视频引擎环境变量提示
        if not self.api_key:
            raise RuntimeError("视频引擎 LLM API Key 未配置（VIDEO_LLM_API_KEY）")
        return super().call(system_prompt, user_prompt, variant=variant, max_length=max_length)


__all__ = ["BaseVideoLLMProvider"]
