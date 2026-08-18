"""LLM call abstraction — wraps provider chat calls with variant support.

Extracted from optimizer.py God Class refactoring (Phase 1).
"""

import logging
from prompt_engine.llm.base import BaseLLMProvider

logger = logging.getLogger(__name__)


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
        logger.info(
            "LLM call: model=%s variant=%d messages=%d system_len=%d user_len=%d",
            self.model_name, variant, len(messages), len(system), len(user_prompt),
        )
        logger.debug("LLM system preview: %s", system[:150] + "..." if len(system) > 150 else system)
        logger.debug("LLM user preview: %s", user_prompt[:150] + "..." if len(user_prompt) > 150 else user_prompt)
        result = self._provider.chat(messages)
        _response_preview = (result[0] or "")[:200]
        logger.info(
            "LLM response: model=%s tokens=%d response_len=%d preview=%s",
            self.model_name, result[1], len(result[0] or ""),
            _response_preview + "..." if len(result[0] or "") > 200 else _response_preview,
        )
        return result

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
        logger.info(
            "LLM call_vision: model=%s messages=%d system_len=%d",
            self.model_name, len(messages), len(system_prompt),
        )
        result = self._provider.chat(messages)
        _response_preview = (result[0] or "")[:200]
        logger.info(
            "LLM vision response: model=%s tokens=%d response_len=%d preview=%s",
            self.model_name, result[1], len(result[0] or ""),
            _response_preview + "..." if len(result[0] or "") > 200 else _response_preview,
        )
        return result

    @property
    def provider(self) -> BaseLLMProvider:
        return self._provider

    @property
    def model_name(self) -> str:
        return self._provider.model_name
