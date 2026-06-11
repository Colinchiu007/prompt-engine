"""讯飞星火 LLM Provider — 基于 WebSocket 流式 API"""

from prompt_engine.llm.base import BaseLLMProvider


class XfyunProvider(BaseLLMProvider):
    """讯飞星火大模型 API"""

    def __init__(self, config: dict):
        super().__init__(config)
        self._app_id = config["app_id"]
        self._api_key = config["api_key"]
        self._api_secret = config["api_secret"]
        self._model = config.get("model", "generalv3.5")
        self._temperature = config.get("temperature", 0.7)
        self._max_tokens = config.get("max_tokens", 500)

    def chat(self, messages: list[dict]) -> tuple[str, int]:
        # TODO: 讯飞 WebSocket API 实现
        # 当前返回占位，后续实现
        raise NotImplementedError("讯飞 Provider 尚在实现中，请使用 openai_compat")

    @property
    def model_name(self) -> str:
        return self._model