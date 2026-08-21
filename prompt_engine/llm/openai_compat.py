"""OpenAI 兼容 API LLM Provider"""
import logging

from openai import OpenAI

from prompt_engine.llm.base import BaseLLMProvider

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
        if not text and reasoning:
            # 纯推理响应：不把思考内容当提示词（fail-closed），只记录诊断，
            # 返回空文本由上层 optimize/调用方既有回退原文逻辑兜底。
            logger.warning(
                "OpenAICompatProvider: content 为空但含推理内容（model=%s finish_reason=%s reasoning_len=%d），返回空文本",
                self._model,
                getattr(response.choices[0], "finish_reason", None),
                len(reasoning),
            )
        tokens = response.usage.total_tokens if response.usage else 0
        return text, tokens

    @property
    def model_name(self) -> str:
        return self._model
