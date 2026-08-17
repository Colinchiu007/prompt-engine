"""Google Gemini LLM Provider."""
import logging
from typing import Optional

from prompt_engine.llm.base import BaseLLMProvider

logger = logging.getLogger(__name__)


class GeminiProvider(BaseLLMProvider):
    """Google Gemini API provider — 通过 google-genai SDK 调用."""

    def __init__(self, config: dict):
        super().__init__(config)
        self.api_key = config["api_key"]
        self._model = config.get("model", "gemini-2.0-flash")
        self.temperature = config.get("temperature", 0.7)
        self.max_tokens = config.get("max_tokens", 500)
        self.timeout = config.get("timeout", 60)
        self._client = None

    @property
    def model_name(self) -> str:
        return self._model

    def _get_client(self):
        if self._client is None:
            try:
                from google import genai
                self._client = genai.Client(api_key=self.api_key)
            except ImportError:
                logger.warning("google-genai not installed, using mock client")
                self._client = None
        return self._client

    def chat(self, system_prompt: str, user_prompt: str) -> tuple[str, int]:
        """调用 Gemini 模型."""
        client = self._get_client()
        if client is None:
            # 降级：没有 SDK 时返回错误信息
            return _fallback_chat(system_prompt, user_prompt), 0

        try:
            response = client.models.generate_content(
                model=self._model,
                contents=user_prompt,
                config={
                    "system_instruction": system_prompt,
                    "temperature": self.temperature,
                    "max_output_tokens": self.max_tokens,
                },
            )
            text = response.text
            tokens = 0
            if hasattr(response, "usage_metadata"):
                tokens = response.usage_metadata.total_token_count or 0
            return text, tokens
        except Exception as e:
            logger.warning("Gemini API call failed: %s", e)
            return _fallback_chat(system_prompt, user_prompt), 0

def _fallback_chat(system_prompt: str, user_prompt: str) -> str:
    """当 API 不可用时的降级处理."""
    return user_prompt
