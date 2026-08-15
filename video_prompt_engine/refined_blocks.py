"""Shared schema and sanitizers for Higgsfield refined prompt blocks."""
from __future__ import annotations

import re
from typing import Any


BLOCK_ORDER = (
    "SCENE NOTE", "SPATIAL LAYOUT", "LIGHTING", "COLOR", "CAMERA",
    "ENVIRONMENT", "CONTINUITY", "CHARACTERS", "SKIN", "ACTING",
    "STILLNESS LOCK", "FINAL FRAME",
)
BLOCK_MAX = 4000
RENDERED_BLOCK_PATTERN_SOURCE = r"^[ \t]*([A-Z][A-Z ]{2,30}):[ \t]*"
RENDERED_BLOCK_RE = re.compile(RENDERED_BLOCK_PATTERN_SOURCE, re.MULTILINE)

_FAIL_CHECK_RE = re.compile(
    r"(?ims)(?:^|\n)[ \t]*(?:"
    r"#{1,6}[ \t]+FAIL CHECK(?:[ \t]*\([^\n)]*\))?[ \t]*"
    r"|FAIL CHECK(?:[ \t]*\([^\n)]*\))?[ \t]*:?[ \t]*)"
    r"[^\n]*(?:\n.*)?\Z"
)
TRAILER_TAIL_RE = re.compile(
    r"\s*Photoreal\.?\s+NON-IP\.?\s+"
    r"[A-Za-z0-9:._/\-]+\.?\s+\d+(?:\.\d+)?s\.\s+"
    r"(?:Audio:[^\n]*|No music\.|[^.\n]+ only\.)\s*$",
    re.IGNORECASE,
)
# 评审 C3：漂移尾行（缺 aspect/duration 的 Photoreal NON-IP 形态）——$ 锚定仅末位、结构校验，
# 与 TRAILER_TAIL_RE 同口径的宽松版（防 append 后再拼规范尾行导致双尾行回归）。
# aspect/duration 槽限数字形态（16:9 / 16x9 / 15s / 5.5s，≤2 次）；audio 槽限单 token only./
# No music./Audio: 段——"aesthetic for reference only." / "aesthetic. No music." 一类
# 描述性字面量因非数字槽位而保留（与 C1/C1-1 中段保护一致）。
DRIFT_TRAILER_RE = re.compile(
    r"\s*Photoreal\.?\s+NON-IP\.?\s+"
    r"(?:(?:[0-9]+(?::|x)[0-9]+|[0-9]+(?:\.[0-9]+)?s)\.?\s+){0,2}"
    r"(?:Audio:[^\n]*|No music\.|[A-Za-z0-9_-]+ only\.)\s*$",
    re.IGNORECASE,
)


def strip_fail_check(value: Any) -> str:
    """Remove an accidentally emitted template-only FAIL CHECK suffix."""
    return _FAIL_CHECK_RE.sub("", str(value or "")).rstrip()


def strip_embedded_trailer(value: Any) -> str:
    """Remove a complete trailer suffix; fall back to a drift trailer (missing aspect/duration)."""
    text = str(value or "")
    stripped = TRAILER_TAIL_RE.sub("", text).rstrip()
    if stripped != text.rstrip():
        return stripped
    return DRIFT_TRAILER_RE.sub("", text).rstrip()


def clean_block_value(key: Any, value: Any) -> str:
    """Normalize one recognized block value with the shared field limit."""
    if key not in BLOCK_ORDER or not isinstance(value, str):
        return ""
    return strip_embedded_trailer(strip_fail_check(value)).strip()[:BLOCK_MAX]


def clean_blocks(value: Any) -> dict[str, str] | None:
    """Normalize the 12-block refined schema and reject unknown/non-string values."""
    if not isinstance(value, dict):
        return None
    cleaned: dict[str, str] = {}
    for key in BLOCK_ORDER:
        text = clean_block_value(key, value.get(key))
        if text:
            cleaned[key] = text
    return cleaned or None


def rendered_block_names(value: Any) -> set[str]:
    """Return recognized line-start block markers from a rendered prompt."""
    return {
        match.group(1).strip()
        for match in RENDERED_BLOCK_RE.finditer(str(value or ""))
        if match.group(1).strip() in BLOCK_ORDER
    }
