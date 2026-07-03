"""OpenAI 兼容 API LLM Provider"""
from typing import Optional
from openai import OpenAI
from prompt_engine.llm.base import BaseLLMProvider


class OpenAICompatProvider(BaseLLMProvider):
    """支持 OpenAI / OpenRouter / DeepSeek 等兼容 API"""

    def __init__(self, config: dict):
        super().__init__(config)
        self._client = OpenAI(
            api_key=config["api_key"],
            base_url=config["base_url"],
            max_retries=3,  # 自动指数退避重试
        )
        self._model = config.get("model", "gpt-4o")
        self._temperature = config.get("temperature", 0.7)
        self._max_tokens = config.get("max_tokens", 500)
        self._timeout = config.get("timeout", 15)

    def chat(self, messages: list[dict]) -> tuple[str, int]:
        """调用 LLM，返回 (响应文本, token消耗)"""
        response = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=self._temperature,
            max_tokens=self._max_tokens,
            timeout=self._timeout,
        )
        text = response.choices[0].message.content or ""
        tokens = response.usage.total_tokens if response.usage else 0
        return text, tokens

    @property
    def model_name(self) -> str:
        return self._model
