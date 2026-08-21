"""OpenAI 兼容 API LLM Provider"""
import logging
import time

from openai import OpenAI

from prompt_engine.llm.base import BaseLLMProvider
from prompt_engine_core.llm import (
    _REASONING_FINAL_OUTPUT_INSTRUCTION,
    _REASONING_RETRY_ATTEMPTS,
    _REASONING_RETRY_INSTRUCTION,
    _REASONING_RETRY_MAX_TOKENS,
)

logger = logging.getLogger(__name__)


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
        # 输出预算交由网关默认：推理模型（如 MiMo/DeepSeek）先思考后输出，
        # 硬编码小预算会把思考耗尽导致 content 为空；显式配置 max_tokens 仍可覆盖。
        self._max_tokens = config.get("max_tokens")
        # 慢推理响应可达数十秒（桌面端同网关实测 27~53s），默认超时放宽到 120s；显式配置可覆盖。
        self._timeout = config.get("timeout", 120)

    @staticmethod
    def _message_chars(messages) -> int:
        """统计消息文本总长度（兼容纯文本与多模态 content 数组）。"""
        total = 0
        for message in messages or []:
            content = message.get("content") if isinstance(message, dict) else getattr(message, "content", "")
            if isinstance(content, str):
                total += len(content)
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and isinstance(part.get("text"), str):
                        total += len(part["text"])
        return total

    def chat(self, messages: list[dict]) -> tuple[str, int]:
        """调用 LLM，返回 (响应文本, token消耗)

        未显式配置 max_tokens 时省略该字段（交由网关默认输出预算），
        与桌面端 OpenAI 兼容适配器行为一致；仅在显式配置时透传。

        Path 2+ — 自动检测推理模型仅输出思考块：
        - content 为空但 reasoning_content 非空时最多重试两次（共三次调用）；
        - 重试指令更明确，并逐步追加 final-output system 指令；
        - 显式配置的小 max_tokens 自动提升到 8192，避免思考耗尽输出预算；
        - 重试仍为空则返回空文本（fail-closed，不伪造提示词），同时记录完整诊断。
        """
        params = {
            "model": self._model,
            "messages": messages,
            "temperature": self._temperature,
            "timeout": self._timeout,
        }
        if isinstance(self._max_tokens, int) and self._max_tokens > 0:
            params["max_tokens"] = self._max_tokens
        _start = time.time()
        logger.info(
            "OpenAICompatProvider request: model=%s messages=%d chars=%d max_tokens=%s timeout=%ds",
            self._model, len(messages), self._message_chars(messages), params.get("max_tokens"), self._timeout,
        )
        response = self._client.chat.completions.create(**params)
        message = response.choices[0].message
        text = message.content or ""
        reasoning = getattr(message, "reasoning_content", None) or ""
        tokens = response.usage.total_tokens if response.usage else 0
        finish_reason = getattr(response.choices[0], "finish_reason", None)
        retries = 0

        if not text and reasoning:
            retry_params = dict(params)
            if isinstance(retry_params.get("max_tokens"), int) and retry_params["max_tokens"] < _REASONING_RETRY_MAX_TOKENS:
                retry_params["max_tokens"] = _REASONING_RETRY_MAX_TOKENS
            for retry in range(_REASONING_RETRY_ATTEMPTS - 1):
                retries += 1
                logger.warning(
                    "OpenAICompatProvider: content 为空但含推理内容（model=%s finish_reason=%s reasoning_len=%d），第 %d 次重试，max_tokens=%s",
                    self._model, finish_reason, len(reasoning), retries, retry_params.get("max_tokens"),
                )
                retry_messages = messages + [
                    {"role": "user", "content": _REASONING_RETRY_INSTRUCTION},
                ]
                if retry >= 1:
                    retry_messages = retry_messages + [
                        {"role": "system", "content": _REASONING_FINAL_OUTPUT_INSTRUCTION},
                    ]
                retry_response = self._client.chat.completions.create(
                    **dict(retry_params, messages=retry_messages)
                )
                retry_message = retry_response.choices[0].message
                text = retry_message.content or ""
                tokens = retry_response.usage.total_tokens if retry_response.usage else 0
                finish_reason = getattr(retry_response.choices[0], "finish_reason", None)
                if text:
                    break
            if not text:
                logger.warning(
                    "OpenAICompatProvider: 重试 %d 次后 content 仍为空（model=%s），返回空文本（fail-closed）",
                    retries, self._model,
                )

        elapsed_ms = int((time.time() - _start) * 1000)
        logger.info(
            "OpenAICompatProvider response: model=%s finish_reason=%s content_len=%d reasoning_len=%d retries=%d latency_ms=%d total_tokens=%d",
            self._model, finish_reason, len(text), len(reasoning), retries, elapsed_ms, tokens,
        )

        return text, tokens

    @property
    def model_name(self) -> str:
        return self._model
