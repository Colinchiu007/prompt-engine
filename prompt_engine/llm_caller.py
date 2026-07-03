"""LLM call abstraction — wraps provider chat calls with variant support.

Extracted from optimizer.py God Class refactoring (Phase 1).
"""

from prompt_engine.llm.base import BaseLLMProvider


class LLMCaller:
    """LLM 调用封装：标准调用 + 视觉调用 + 变体注入"""

    def __init__(self, provider: BaseLLMProvider):
        self._provider = provider

    def call(
        self, system_prompt: str, user_prompt: str, variant: int = 0,
    ) -> tuple[str, int]:
        """调用 LLM，可选变体编号注入"""
        system = system_prompt
        if variant > 0:
            system += (
                f"\n\nIMPORTANT: This is variant {variant + 1}. "
                "Generate a DIFFERENT version from a different creative angle "
                "or perspective. Do NOT repeat the same structure as previous versions."
            )

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_prompt},
        ]
        return self._provider.chat(messages)

    def call_vision(
        self, system_prompt: str, image_url: str, detail: str = "auto",
    ) -> tuple[str, int]:
        """调用视觉 LLM 分析图片"""
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Analyze this image and generate a detailed image generation prompt for it.",
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": image_url, "detail": detail},
                    },
                ],
            },
        ]
        return self._provider.chat(messages)

    @property
    def provider(self) -> BaseLLMProvider:
        return self._provider

    @property
    def model_name(self) -> str:
        return self._provider.model_name
