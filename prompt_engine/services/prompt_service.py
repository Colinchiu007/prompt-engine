"""调用方 BYOK 的场景文案到图片提示词服务。"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import List, Optional

from prompt_engine.llm.base import BaseLLMProvider
from prompt_engine.models import LLMBind, OptimizeRequest

try:
    from prompt_engine.optimizer import Optimizer
except ImportError:  # pragma: no cover
    Optimizer = None  # type: ignore


@dataclass
class OptimizePromptResult:
    prompts: List[str]
    error: Optional[str] = None


def _normalize_llm(llm: LLMBind | dict | None) -> LLMBind | None:
    if llm is None:
        return None
    if isinstance(llm, LLMBind):
        return llm
    return LLMBind.model_validate(llm)


def _provider_identity(llm: LLMBind) -> str:
    key_digest = hashlib.sha256(llm.api_key.encode("utf-8")).hexdigest()[:16]
    return (
        f"{llm.caller or ''}|{llm.provider}|{llm.model}|{llm.base_url or ''}"
        f"|key:{key_digest}"
    )


def _missing_llm_result() -> OptimizePromptResult:
    return OptimizePromptResult(
        prompts=[],
        error="llm 必填：场景提示词优化必须使用调用方传入的模型绑定",
    )


async def optimize_prompt(
    text: str,
    segments: Optional[List[str]] = None,
    system_prompt: Optional[str] = None,
    llm: LLMBind | dict | None = None,
) -> OptimizePromptResult:
    """使用调用方传入的 LLM 优化场景文案。

    本服务不读取环境变量或 config.yaml 中的文字 LLM Key。system_prompt
    保留为接口参数，具体平台系统提示词由 prompt-engine Optimizer 统一生成。
    """
    del system_prompt
    bind = _normalize_llm(llm)
    if bind is None:
        return _missing_llm_result()
    if Optimizer is None:  # pragma: no cover
        return OptimizePromptResult(prompts=[], error="prompt-engine Optimizer 不可用")

    try:
        provider = BaseLLMProvider.from_llm_object(bind)
        optimizer = Optimizer()
        inputs = segments if segments is not None else [text]
        prompts: List[str] = []
        provider_id = _provider_identity(bind)

        for segment in inputs:
            if not segment or not segment.strip():
                continue
            request = OptimizeRequest(
                prompt=segment,
                platform="generic",
                llm=bind,
            )
            result = optimizer.optimize(
                request,
                provider=provider,
                provider_id=provider_id,
            )
            if result.error:
                return OptimizePromptResult(prompts=[], error=result.error)
            if result.optimized_prompt and result.optimized_prompt.strip():
                prompts.append(result.optimized_prompt.strip())

        return OptimizePromptResult(prompts=prompts)
    except ValueError as exc:
        return OptimizePromptResult(prompts=[], error=str(exc))
    except Exception as exc:  # noqa: BLE001
        return OptimizePromptResult(prompts=[], error=f"提示词优化失败：{exc}")


async def optimize_prompts_batch(
    scenes: List[dict],
    llm: LLMBind | dict | None = None,
) -> OptimizePromptResult:
    """使用同一个调用方 LLM 绑定批量优化多个场景。"""
    if llm is None:
        return _missing_llm_result()
    texts = [scene.get("text", "") for scene in scenes]
    return await optimize_prompt(
        text="",
        segments=texts,
        llm=llm,
    )
