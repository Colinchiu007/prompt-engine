"""MiniMax LLM Provider — OpenAI 兼容 API（MiniMax-M3 模型）"""
from openai import OpenAI
import logging
import time
from prompt_engine.llm.base import BaseLLMProvider

logger = logging.getLogger(__name__)


class MiniMaxProvider(BaseLLMProvider):
    """MiniMax 大模型 — 通过 OpenAI 兼容 API 调用"""

    def __init__(self, config: dict):
        super().__init__(config)
        self._client = OpenAI(
            api_key=config["api_key"],
            base_url=config.get("base_url", "https://api.minimaxi.com/v1"),
            max_retries=3,
        )
        self._model = config.get("model", "MiniMax-M3")
        self._temperature = config.get("temperature", 0.7)
        self._max_tokens = config.get("max_tokens", 500)
        self._timeout = config.get("timeout", 60)

    def chat(self, messages: list) -> tuple:
        _start = time.time()
        _key_prefix = self._client.api_key[:8] + "..." if self._client.api_key and len(self._client.api_key) > 8 else self._client.api_key
        _total_chars = sum(len(m.get("content", "") if isinstance(m.get("content"), str) else str(m.get("content", ""))) for m in messages)
        logger.info(
            "MiniMax request: model=%s base_url=%s messages=%d total_chars=%d temp=%.1f max_tokens=%d timeout=%ds key=%s",
            self._model, self._client.base_url, len(messages), _total_chars,
            self._temperature, self._max_tokens, self._timeout, _key_prefix,
        )
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=self._temperature,
                max_tokens=self._max_tokens,
                timeout=self._timeout,
            )
            text = response.choices[0].message.content or ""
            tokens = response.usage.total_tokens if response.usage else 0
            prompt_tokens = response.usage.prompt_tokens if response.usage else 0
            completion_tokens = response.usage.completion_tokens if response.usage else 0
            elapsed_ms = int((time.time() - _start) * 1000)
            logger.info(
                "MiniMax response: model=%s tokens=%d (prompt=%d completion=%d) latency_ms=%d output_len=%d",
                self._model, tokens, prompt_tokens, completion_tokens, elapsed_ms, len(text),
            )
            return text, tokens
        except Exception as e:
            elapsed_ms = int((time.time() - _start) * 1000)
            logger.error("MiniMax error: model=%s latency_ms=%d key=%s error=%s", self._model, elapsed_ms, _key_prefix, str(e)[:300])
            raise

    @property
    def model_name(self) -> str:
        return self._model
