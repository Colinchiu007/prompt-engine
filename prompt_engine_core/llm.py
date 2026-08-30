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

# Path 2+ — 推理模型仅输出思考块（content 为空）时的自动重试指令。
# 告知模型：之前的响应只包含推理内容，现在请把实际回复放在 content 字段。
# 不伪造/拼接提示词（fail-closed）：若重试仍为空，_request 返回 None，
# 由上层 optimizer 的模板优化兜底（图片域）或回退原文（视频域）处理。
_REASONING_RETRY_INSTRUCTION = (
    "You have previously output only thinking/reasoning content without a visible "
    "response in the content field. Please provide your complete actual response "
    "in the content field now, following the output format specified in the system prompt. "
    "Do NOT include any thinking blocks in the content field."
)
_REASONING_FINAL_OUTPUT_INSTRUCTION = (
    "You must return the complete final answer as the visible content field now. "
    "Do NOT output thinking, reasoning, or hidden tags in the content field."
)
_REASONING_RETRY_ATTEMPTS = 3
_REASONING_RETRY_MAX_TOKENS = 8192

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

    def _raw_request(
        self, messages: list[dict], max_tokens: int, url: str, headers: dict
    ) -> tuple[str | None, str]:
        """执行单次 LLM HTTP 请求。

        返回 (content, reasoning_content)。
        - content 可能为 None（推理模型仅输出思考块）；
        - reasoning_content 始终为字符串（空表示模型未提供推理）。
        """
        payload = {
            "model": self.model or "gpt-4o-mini",
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": max_tokens,
        }
        req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers)
        _start = time.time()
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            data = json.loads(resp.read().decode())
        message = data["choices"][0]["message"]
        content = message.get("content")
        reasoning = message.get("reasoning_content") or ""
        logger.info(
            "BaseLLMProvider raw: model=%s max_tokens=%d content_len=%d reasoning_len=%d latency_ms=%d",
            self.model, max_tokens, len(content or ""), len(reasoning),
            int((time.time() - _start) * 1000),
        )
        return content, reasoning

    def _request(self, system_prompt: str, user_prompt: str, max_tokens: int = 3000) -> str | None:
        """调用 LLM，返回 content 文本（可能为 None）。

        部分网关（推理模型）可能缺 content 键或 content 为 null：安全读取，不抛 KeyError。

        Path 2+ — 自动检测推理模型仅输出思考块的情况：
        - content 为空但 reasoning_content 非空时最多重试两次（共三次调用）；
        - 每次重试追加用户指令，最后一次追加 final-output system 指令；
        - 重试预算提升到 8192（仍受 max_tokens_cap 约束），避免思考耗尽输出预算；
        - 重试仍为空则返回 None（fail-closed），由上层 optimizer 模板兜底或回退原文。
        """
        url = f"{self.base_url}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        logger.info(
            "BaseLLMProvider request: model=%s max_tokens=%d system_len=%d user_len=%d",
            self.model, max_tokens, len(system_prompt), len(user_prompt),
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        content, reasoning = self._raw_request(messages, max_tokens, url, headers)
        retries = 0

        while not (content and content.strip()) and reasoning:
            if retries >= _REASONING_RETRY_ATTEMPTS - 1:
                break
            retries += 1
            logger.warning(
                "BaseLLMProvider: content 为空但含推理内容（model=%s reasoning_len=%d attempt=%d/%d），重试",
                self.model, len(reasoning), retries, _REASONING_RETRY_ATTEMPTS,
            )
            messages.append({"role": "user", "content": _REASONING_RETRY_INSTRUCTION})
            if retries >= 2:
                messages.append({"role": "system", "content": _REASONING_FINAL_OUTPUT_INSTRUCTION})
            retry_max_tokens = max(max_tokens, _REASONING_RETRY_MAX_TOKENS)
            if self.max_tokens_cap:
                retry_max_tokens = min(retry_max_tokens, self.max_tokens_cap)
            content, reasoning = self._raw_request(messages, retry_max_tokens, url, headers)

        if not (content and content.strip()):
            logger.warning(
                "BaseLLMProvider: content 仍为空（model=%s attempts=%d），返回 None（fail-closed）",
                self.model, retries,
            )

        return content

    def call(self, system_prompt: str, user_prompt: str, variant: int = 0, max_length: int | None = None) -> tuple[str, int]:
        """返回 (content, tokens)。无 key 时抛错（fail closed）。

        max_tokens 按 max_length 动态放大（refined 长模板 ≤40000 字符），
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
