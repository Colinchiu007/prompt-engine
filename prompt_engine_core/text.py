"""文本工具 — 跨引擎共享的模型输出清洗机械件。

来源：视频引擎 optimizer.strip_reasoning_blocks / strategies.base._clamp_int，
提炼为通用工具；两引擎均复用同一实现，禁止再复制。
"""
from __future__ import annotations

import re
from typing import Any


def strip_reasoning_blocks(text: str | None) -> str:
    """剥离模型输出中的推理块（<think>...</think>），返回实际提示词内容。

    带推理能力的模型（如 MiniMax-M2.7）可能把思考过程写进返回内容：
    - 完整推理块 <think>...</think>：移除后保留 </think> 之后的内容；
    - 无闭合标签的 <think> 前缀：视为没有实际内容，返回空串（由调用方回退原文）。
    """
    if not text:
        return text or ""
    stripped = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    lower = stripped.lower()
    think_idx = lower.find("<think>")
    if think_idx >= 0:
        stripped = stripped[:think_idx]
    return stripped.strip()


def strip_json_fences(text: str) -> str:
    """剥离 markdown code fence（```json ... ``` 或 ``` ... ```），返回裸 JSON 文本。"""
    if not text:
        return text
    stripped = text.strip()
    m = re.match(r"^```(?:json)?\s*\n(.*?)\n```$", stripped, flags=re.DOTALL)
    if m:
        return m.group(1).strip()
    return stripped


def clamp_int(value: Any, lo: int, hi: int, default: int) -> int:
    """数值钳制：解析失败回退 default，越界收敛到 [lo, hi]。"""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


def clamp_float(value: Any, lo: float, hi: float, default: float) -> float:
    """浮点钳制：解析失败回退 default，越界收敛到 [lo, hi]。"""
    try:
        n = float(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


def clean_str_list(value: Any, limit: int) -> list[str]:
    """字符串列表清洗：仅保留 strip 后非空项，截断到 limit。"""
    if not isinstance(value, list):
        return []
    return [str(v).strip() for v in value if str(v or "").strip()][:limit]
