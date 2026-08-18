"""讯飞星火 LLM Provider — OpenAI 兼容 API（maas-coding-api）"""
from openai import OpenAI
import logging
import time
from prompt_engine.llm.base import BaseLLMProvider

logger = logging.getLogger(__name__)


class XfyunProvider(BaseLLMProvider):
    """讯飞星火大模型 — 通过 OpenAI 兼容 API 调用"""

    def __init__(self, config: dict):
        super().__init__(config)
        self._client = OpenAI(
            api_key=config["api_key"],
            base_url=config["base_url"],
            max_retries=3,
        )
        self._model = config.get("model", "astron-code-latest")
        self._temperature = config.get("temperature", 0.7)
        self._max_tokens = config.get("max_tokens", 500)
        self._timeout = config.get("timeout", 60)

    def chat(self, messages: list) -> tuple:
        _start = time.time()
        logger.info("Xfyun request: model=%s base_url=%s messages=%d", self._model, self._client.base_url, len(messages))
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
            elapsed_ms = int((time.time() - _start) * 1000)
            logger.info("Xfyun response: model=%s tokens=%d latency_ms=%d", self._model, tokens, elapsed_ms)
            return text, tokens
        except Exception as e:
            elapsed_ms = int((time.time() - _start) * 1000)
            logger.error("Xfyun error: model=%s latency_ms=%d error=%s", self._model, elapsed_ms, str(e)[:200])
            raise

    @property
    def model_name(self) -> str:
        return self._model
