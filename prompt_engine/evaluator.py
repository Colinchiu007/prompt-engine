"""Prompt 评估对比模式 — LLM 驱动的多维度评估."""
import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class EvaluationDimension(str, Enum):
    """评估维度."""
    CLARITY = "clarity"                 # 清晰度
    SPECIFICITY = "specificity"         # 具体度
    CREATIVITY = "creativity"           # 创意度
    ACTIONABILITY = "actionability"     # 可执行性 (LLM 能否理解)
    PLATFORM_BEST = "platform_best"     # 平台最佳实践


@dataclass
class DimensionScore:
    """单个维度的评分."""
    before: int = 1
    after: int = 1

    @property
    def improvement(self) -> str:
        delta = self.after - self.before
        return f"+{delta}" if delta >= 0 else str(delta)


@dataclass
class EvaluationResult:
    """完整的评估结果."""
    original: str
    optimized: str
    scores: dict[str, DimensionScore]
    overall_improvement: float = 0.0
    platform: str = "generic"


def _build_evaluation_prompt(original: str, optimized: str, platform: str = "generic") -> str:
    """构造评估 prompt."""
    return f"""请从以下维度评估两段 prompt 的质量，按 1-10 打分。

原始 prompt: "{original}"
优化后 prompt: "{optimized}"
平台: {platform}

评分维度：
1. clarity (清晰度) — prompt 表达是否清晰无歧义
2. specificity (具体度) — 是否包含足够的视觉细节
3. creativity (创意度) — 是否有创意和想象力
4. actionability (可执行性) — AI 模型能否准确理解并执行
5. platform_best (平台最佳实践) — 是否符合该平台的最佳写法

请严格按以下 JSON 格式返回，不要加额外说明：
{{
  "clarity": {{"before": 3, "after": 8}},
  "specificity": {{"before": 2, "after": 9}},
  "creativity": {{"before": 5, "after": 7}},
  "actionability": {{"before": 4, "after": 8}},
  "platform_best": {{"before": 3, "after": 9}}
}}
每个分数 1-10 整数。"""


def _call_llm_for_evaluation(original: str, optimized: str, platform: str = "generic") -> dict:
    """调用 LLM 进行评估（使用 prompt-engine 自身的 Optimizer 的 provider）."""
    from prompt_engine.config import load_config
    from prompt_engine.llm import create_provider

    config = load_config()
    provider_name = config.get("llm", {}).get("provider", "openai_compat")
    provider_config = config.get("llm", {}).get(provider_name, {})

    try:
        provider = create_provider(provider_name, **provider_config)
        prompt = _build_evaluation_prompt(original, optimized, platform)
        response, _ = provider.chat("你是一位 prompt 质量评估专家。", prompt)
        return _parse_evaluation_response(response)
    except Exception as e:
        logger.warning("LLM evaluation failed: %s", e)
        return _fallback_scores()


def _parse_evaluation_response(response: str) -> dict:
    """解析 LLM 返回的 JSON 评分."""
    try:
        # 尝试提取 JSON
        json_match = re.search(r"\{[^{}]*\"before\"[^{}]*\"after\"[^{}]*\}", response, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            return data
        # 尝试整体解析
        data = json.loads(response)
        return data
    except Exception:
        logger.debug("Failed to parse evaluation response, using fallback")
        return _fallback_scores()


def _fallback_scores() -> dict:
    """LLM 不可用时的兜底评分。"""
    return {
        "clarity": {"before": 5, "after": 5},
        "specificity": {"before": 5, "after": 5},
        "creativity": {"before": 5, "after": 5},
        "actionability": {"before": 5, "after": 5},
        "platform_best": {"before": 5, "after": 5},
    }


def evaluate(
    original: str,
    optimized: str,
    platform: str = "generic",
) -> EvaluationResult:
    """评估两段 prompt 的质量对比.

    Args:
        original: 原始 prompt
        optimized: 优化后的 prompt
        platform: 目标平台

    Returns:
        EvaluationResult 包含各维度评分和总体改进率
    """
    if not original.strip():
        original = "(empty)"

    scores_dict = _call_llm_for_evaluation(original, optimized, platform)

    scores: dict[str, DimensionScore] = {}
    total_before = 0
    total_after = 0
    count = 0

    for dim, vals in scores_dict.items():
        if isinstance(vals, dict) and "before" in vals and "after" in vals:
            ds = DimensionScore(
                before=max(1, min(10, int(vals.get("before", 5)))),
                after=max(1, min(10, int(vals.get("after", 5)))),
            )
            scores[dim] = ds
            total_before += ds.before
            total_after += ds.after
            count += 1

    overall = 0.0
    if count > 0 and total_before > 0:
        overall = round(((total_after - total_before) / total_before) * 100, 1)

    return EvaluationResult(
        original=original,
        optimized=optimized,
        scores=scores,
        overall_improvement=overall,
        platform=platform,
    )
