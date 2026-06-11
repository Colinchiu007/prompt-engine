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

    def chat(self, messages: list[dict], n: int = 1) -> tuple[str, int]:
        """调用 LLM，返回 (响应文本, token消耗)
        
        Args:
            messages: 消息列表
            n: 生成数量，用于 A/B 多候选
        """
        response = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=self._temperature,
            max_tokens=self._max_tokens,
            timeout=self._timeout,
            n=n,
        )
        # 如果 n>1，合并为多候选
        texts = []
        tokens = 0
        for choice in response.choices:
            texts.append(choice.message.content or "")
            tokens += choice.usage.prompt_tokens + choice.usage.completion_tokens if choice.usage else 0
        if len(texts) == 1:
            return texts[0], tokens
        return "\n---\n".join(texts), tokens

    @property
    def model_name(self) -> str:
        return self._model
