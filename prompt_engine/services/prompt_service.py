"""Prompt optimization service — scene-to-prompt, with prompt-engine fallback.

This module provides the higher-level optimization service that:
1. Takes raw scene text (not platform-specific prompts)
2. Optionally segments the text for batch processing
3. Uses prompt-engine's platform-specific Optimizer when available
4. Falls back to a direct LLM call for generic optimization

Note: this is the migrated home from platform-orchestrator/services/prompt_service.py.
The old location now contains a deprecation shim.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Optional

import httpx

# ── Optional prompt-engine Optimizer ─────────────────────────────────────
# Import directly from the optimizer submodule to avoid circular imports
# through prompt_engine/__init__.py's __getattr__.
_HAS_PROMPT_ENGINE = False
try:
    from prompt_engine.optimizer import Optimizer
    _HAS_PROMPT_ENGINE = True
except ImportError:  # pragma: no cover
    Optimizer = None  # type: ignore


# ── Default System Prompt ────────────────────────────────────────────────

DEFAULT_SYSTEM_PROMPT = """你是一位专业的AI图像生成提示词专家。
请将以下场景描述优化为高质量的图像生成提示词。

要求：
1. 描述视觉元素：主体、环境、光线、色彩、构图
2. 指定艺术风格和氛围
3. 添加必要的技术参数（比例、画质等）
4. 保持与原文的语义一致性
5. 输出简洁、精准的英文或中文提示词

直接输出优化后的提示词，不要包含解释性文字。"""


# ── Data Models ──────────────────────────────────────────────────────────


@dataclass
class OptimizePromptResult:
    prompts: List[str]
    error: Optional[str] = None


# ── Fallback LLM Call (async, OpenAI-compatible) ─────────────────────────


async def _call_llm(
    api_key: str,
    base_url: str,
    model: str,
    system_prompt: str,
    user_content: str,
    timeout: int = 120,
) -> str:
    """Call OpenAI-compatible LLM API via HTTPX.

    This is a self-contained fallback used when prompt-engine's Optimizer
    is not available or raises an error.
    """
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                "temperature": 0.7,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


# ── Public API ───────────────────────────────────────────────────────────


async def optimize_prompt(
    text: str,
    segments: Optional[List[str]] = None,
    system_prompt: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
) -> OptimizePromptResult:
    """Optimize scene text into image generation prompts.

    Args:
        text: Full scene text or primary prompt input.
        segments: Optional list of sub-segments to optimize individually.
        system_prompt: Custom system prompt (defaults to built-in).
        api_key: LLM API key override (defaults to OPENAI_API_KEY env).
        base_url: LLM base URL override (defaults to OPENAI_BASE_URL env).
        model: LLM model override (defaults to env or gpt-4o-mini).

    Returns:
        OptimizePromptResult with list of optimized prompts.
    """
    key = api_key or os.environ.get("OPENAI_API_KEY", "")
    url = base_url or os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    mdl = model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

    if not key:
        return OptimizePromptResult(prompts=[], error="No LLM API key configured")

    # ── Try prompt-engine's platform-specific optimizer first ────────────
    if _HAS_PROMPT_ENGINE:
        try:
            optim = Optimizer()
            inputs = segments if segments else [text]
            from prompt_engine.models import OptimizeRequest

            all_prompts: List[str] = []
            for segment in inputs:
                if not segment.strip():
                    continue
                req = OptimizeRequest(
                    prompt=segment,
                    platform="generic",
                    style="cinematic",
                )
                result = optim.optimize(req)
                if result.optimized_prompt:
                    all_prompts.append(result.optimized_prompt)
            if all_prompts:
                return OptimizePromptResult(prompts=all_prompts)
        except Exception:
            # Fall back to generic LLM call below
            pass

    sys_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT

    prompts: List[str] = []
    inputs = segments if segments else [text]

    for segment in inputs:
        if not segment.strip():
            continue

        try:
            result = await _call_llm(
                api_key=key,
                base_url=url,
                model=mdl,
                system_prompt=sys_prompt,
                user_content=segment,
            )
            prompts.append(result.strip())
        except Exception as e:
            prompts.append(f"[ERROR] {str(e)}")

    return OptimizePromptResult(prompts=prompts)


async def optimize_prompts_batch(
    scenes: List[dict],
    api_key: Optional[str] = None,
) -> OptimizePromptResult:
    """Optimize prompts for multiple scenes at once.

    Each scene dict should have 'text' key (the scene text to optimize).

    Args:
        scenes: List of scene dicts with 'text' field.
        api_key: LLM API key.

    Returns:
        OptimizePromptResult with one prompt per scene.
    """
    texts = [s.get("text", "") for s in scenes]
    return await optimize_prompt(text="", segments=texts, api_key=api_key)
