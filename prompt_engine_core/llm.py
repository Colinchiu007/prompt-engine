"""LLM 传输层 — 跨引擎共享的 OpenAI 兼容调用（超时 + 动态 max_tokens + fail closed）。

来源：视频引擎 llm/base.py BaseVideoLLMProvider（已含超时重试/动态 max_tokens/默认 base_url），
提炼为通用实现；两引擎共用同一传输语义，领域层（system prompt 构建）保留在各自引擎。
"""
from __future__ import annotations

import json
import logging
import time
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URLS = {
    "openai_compat": "https://api.openai.com/v1",
    "minimax": "https://api.minimax.chat/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta",
}


class BaseLLMProvider:
    """OpenAI 兼容 chat completions 调用（含超时与动态 max_tokens）。"""

    def __init__(self, config: dict):
        llm_cfg = config.get("llm", {})
        self.provider = llm_cfg.get("provider", "openai_compat")
        self.model = llm_cfg.get("model", "")
        self.api_key = llm_cfg.get("api_key", "")
        self.base_url = (llm_cfg.get("base_url") or "").rstrip("/")
        self.timeout = float(llm_cfg.get("timeout", 60))
        # 上游模型硬性 max_tokens 上限可配置（0/缺省=不限制）
        try:
            self.max_tokens_cap = int(llm_cfg.get("max_tokens_cap") or 0) or None
        except (TypeError, ValueError):
            self.max_tokens_cap = None
        if not self.model and self.provider == "minimax":
            self.model = "MiniMax-M2.7"
        if not self.base_url:
            self.base_url = _DEFAULT_BASE_URLS.get(self.provider, "https://api.openai.com/v1")

    @property
    def model_name(self) -> str:
        return self.model or self.provider

    def _request(self, system_prompt: str, user_prompt: str, max_tokens: int = 3000) -> str:
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
        req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers)
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            data = json.loads(resp.read().decode())
        return data["choices"][0]["message"]["content"]

    def call(self, system_prompt: str, user_prompt: str, variant: int = 0, max_length: int | None = None) -> tuple[str, int]:
        """返回 (content, tokens)。无 key 时抛错（fail closed）。

        max_tokens 按 max_length 动态放大（refined 长模板 ≤20000 字符），
        固定 3000 会让 JSON 截断 → 重试耗尽 → 静默回退原文。
        W1：默认 cap 16384（gpt-4o 级常见输出上限），防长模板 max_tokens 溢出被上游 400 拒绝；
        需更大输出时配置 llm.max_tokens_cap。
        """
        if not self.api_key:
            raise RuntimeError("LLM API Key 未配置")
        max_tokens = max(3000, int((max_length or 1800) * 2))
        max_tokens = min(max_tokens, self.max_tokens_cap or 16384)
        t0 = time.time()
        content = self._request(system_prompt, user_prompt, max_tokens=max_tokens)
        tokens = int((time.time() - t0) * 10)  # 粗略估算
        return content, tokens
