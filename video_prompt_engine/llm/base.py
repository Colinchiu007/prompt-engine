"""视频引擎 LLM 供应商（独立实现；支持 openai_compat/minimax/gemini 语义）。"""
from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


class BaseVideoLLMProvider:
    """OpenAI 兼容 chat completions 调用（含超时与重试）。"""

    def __init__(self, config: dict):
        llm_cfg = config.get("llm", {})
        self.provider = llm_cfg.get("provider", "openai_compat")
        self.model = llm_cfg.get("model", "")
        self.api_key = llm_cfg.get("api_key", "")
        self.base_url = (llm_cfg.get("base_url") or "").rstrip("/")
        self.timeout = float(llm_cfg.get("timeout", 60))
        # I4：上游模型硬性 max_tokens 上限可配置（0/缺省=不限制）
        try:
            self.max_tokens_cap = int(llm_cfg.get("max_tokens_cap") or 0) or None
        except (TypeError, ValueError):
            self.max_tokens_cap = None
        if not self.model and self.provider == "minimax":
            self.model = "MiniMax-M2.7"
        if not self.base_url:
            self.base_url = {
                "openai_compat": "https://api.openai.com/v1",
                "minimax": "https://api.minimax.chat/v1",
                "gemini": "https://generativelanguage.googleapis.com/v1beta",
            }.get(self.provider, "https://api.openai.com/v1")

    @property
    def model_name(self) -> str:
        return self.model or self.provider

    def _request(self, system_prompt: str, user_prompt: str, max_tokens: int = 3000) -> str:
        import urllib.request
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model or "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.7,
            "max_tokens": max_tokens,
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(url, data=__import__("json").dumps(payload).encode(), headers=headers)
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            data = __import__("json").loads(resp.read().decode())
        return data["choices"][0]["message"]["content"]

    def call(self, system_prompt: str, user_prompt: str, variant: int = 0, max_length: int | None = None) -> tuple[str, int]:
        """返回 (content, tokens)。无 key 时抛错（fail closed）。

        C2：max_tokens 按 max_length 动态放大（refined 长模板 ≤5000 字符），
        固定 3000 会让 JSON 截断 → 重试耗尽 → 静默回退原文。
        """
        if not self.api_key:
            raise RuntimeError("视频引擎 LLM API Key 未配置（VIDEO_LLM_API_KEY）")
        max_tokens = max(3000, int((max_length or 1800) * 2))
        if self.max_tokens_cap:
            max_tokens = min(max_tokens, self.max_tokens_cap)
        t0 = time.time()
        content = self._request(system_prompt, user_prompt, max_tokens=max_tokens)
        tokens = int((time.time() - t0) * 10)  # 粗略估算
        return content, tokens
