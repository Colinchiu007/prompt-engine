"""OpenAI 兼容 API LLM Provider"""
import logging

from openai import OpenAI

from prompt_engine.llm.base import BaseLLMProvider
from prompt_engine_core.llm import _REASONING_RETRY_INSTRUCTION

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

    def chat(self, messages: list[dict]) -> tuple[str, int]:
        """调用 LLM，返回 (响应文本, token消耗)

        未显式配置 max_tokens 时省略该字段（交由网关默认输出预算），
        与桌面端 OpenAI 兼容适配器行为一致；仅在显式配置时透传。

        Path 2 — 自动检测推理模型仅输出思考块的情况：
        若 content 为空但 reasoning_content 非空，追加指令重试一次，
        引导模型把实际回复输出到 content 字段。普通模型（content 非空）不受影响。
        重试仍为空则返回空文本（fail-closed，不伪造提示词），由上层回退原文逻辑兜底。
        """
        params = {
            "model": self._model,
            "messages": messages,
            "temperature": self._temperature,
            "timeout": self._timeout,
        }
        if isinstance(self._max_tokens, int) and self._max_tokens > 0:
            params["max_tokens"] = self._max_tokens
        response = self._client.chat.completions.create(**params)
        message = response.choices[0].message
        text = message.content or ""
        reasoning = getattr(message, "reasoning_content", None) or ""
        tokens = response.usage.total_tokens if response.usage else 0

        if not text and reasoning:
            # Path 2：纯推理响应 — 记录诊断，自动重试引导输出到 content 字段（fail-closed，不伪造提示词）
            logger.warning(
                "OpenAICompatProvider: content 为空但含推理内容（model=%s finish_reason=%s reasoning_len=%d），自动重试",
                self._model,
                getattr(response.choices[0], "finish_reason", None),
                len(reasoning),
            )
            retry_messages = messages + [
                {"role": "user", "content": _REASONING_RETRY_INSTRUCTION},
            ]
            retry_response = self._client.chat.completions.create(
                **{**params, "messages": retry_messages}
            )
            retry_message = retry_response.choices[0].message
            text = retry_message.content or ""
            tokens = retry_response.usage.total_tokens if retry_response.usage else 0
            if not text:
                logger.warning(
                    "OpenAICompatProvider: 重试后 content 仍为空（model=%s），返回空文本（fail-closed）",
                    self._model,
                )

        return text, tokens

    @property
    def model_name(self) -> str:
        return self._model
