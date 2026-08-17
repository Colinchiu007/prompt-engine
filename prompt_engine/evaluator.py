"""Prompt 评估对比模式 — LLM 驱动的多维度评估."""
import json
import logging
import re
from dataclasses import dataclass, field
from prompt_engine_core.knowledge import load_element_keywords
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


def _call_llm_for_evaluation(original: str, optimized: str, platform: str = "generic", provider=None) -> dict:
    """使用调用方提供的 BYOK provider 评估优化结果。"""
    if provider is None:
        raise ValueError("评估需要调用方传入 llm 绑定；引擎不使用服务端 key 兜底")

    try:
        prompt = _build_evaluation_prompt(original, optimized, platform)
        response, _ = provider.chat([
            {"role": "system", "content": "你是一位 prompt 质量评估专家。"},
            {"role": "user", "content": prompt},
        ])
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
    provider=None,
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

    scores_dict = _call_llm_for_evaluation(original, optimized, platform, provider)

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


# ─────────────────────────────────────────────────────────────────────────────
# 确定性启发式评分（Higgsfield 对齐 — spec: image-prompt-quality）
# 语义与 video_prompt_engine/evaluator.py（origin/main）对齐；命名 evaluate_quality
# 避免与上方 LLM 对比评估 evaluate() 冲突。未来可收敛共享内核（单独 change）。
# ─────────────────────────────────────────────────────────────────────────────


def count_words(text: str) -> int:
    """词数统计（与视频引擎语义一致）。"""
    return len(str(text or "").split())


def _contains_word(text: str, token: str) -> bool:
    """整名/词边界匹配：空 token 与单字符拒绝（中文"关"会误击"关键"）；英文按字母数字边界。"""
    token = str(token or "").strip()
    if not token or len(token) < 2:
        return False
    return (
        re.search(
            r"(?<![A-Za-z0-9])" + re.escape(token) + r"(?![A-Za-z0-9])",
            str(text or ""),
            flags=re.IGNORECASE,
        )
        is not None
    )


def _strip_reference_markers(text: str) -> str:
    """剥离引用协议标记区段（[ABSENT] <name> / <<<...>>>），避免合规标记自罚分。

    仅剥离标记 token 本身（+紧跟一个名字 token），标记后的同句真实出现仍会命中。
    """
    stripped = str(text or "")
    stripped = re.sub(r"<<<.*?>>>", "", stripped, flags=re.DOTALL)
    stripped = re.sub(r"<<<\s*\S+", "", stripped)
    stripped = re.sub(r"\[ABSENT\]\s*\S+", "", stripped, flags=re.IGNORECASE)
    return stripped


def detect_tier(prompt: str, meta: dict | None = None, explicit_tier: str | None = None) -> str:
    """tier 判定：explicit（optimizer 按 creative_level≥7 传入 refined/batch）优先；
    无 explicit 时 auto 兜底——图片域无 shots/NON-IP/FINAL FRAME 概念，恒判 batch。"""
    if explicit_tier in ("refined", "batch"):
        return explicit_tier
    return "batch"


def evaluate_quality(
    prompt: str,
    meta: dict | None = None,
    source_prompt: str = "",
    language: str = "en",
    tier: str | None = None,
    max_length: int | None = None,
) -> dict:
    """确定性启发式评分（无 LLM 调用）：返回 {score: 0-100, checks, tier, violations}。

    图片领域适配（design D2/D3）：
    - tier 长度波段：batch en 30-`min(max(300, max_length//6), 500)` 词 / zh 60-`min(max(1000, max_length), 2000)` 字符；
      refined en `min(500, max(60, max_length//5))`-`min(max(500, max_length//2), 2000)` 词 / zh 300-`max_length` 字符。
    - violations 图片子集：excluded_present -10、swap_source_present -10；无 trailer/audio 概念。
    - 评分权重：长度 20 + 六要素 30 + 保真 20（无镜头字段，/0.7 归一），叠加违规扣分，下限 0。
    """
    checks: dict = {}
    meta = meta or {}
    tier = detect_tier(prompt, meta, explicit_tier=tier)
    checks["tier"] = tier

    # 1) 层级长度波段
    words = count_words(prompt)
    max_len = max_length or 500
    if language == "zh":
        if tier == "refined":
            length_ok = 300 <= len(str(prompt)) <= max_len
        else:
            length_ok = 60 <= len(str(prompt)) <= min(max(1000, max_len), 2000)
    else:
        if tier == "refined":
            lower = min(500, max(60, max_len // 5))
            upper = min(max(500, max_len // 2), 2000)
            length_ok = lower <= words <= upper
        else:
            upper = min(max(300, max_len // 6), 500)
            length_ok = 30 <= words <= upper
    checks["length"] = length_ok
    checks["words"] = words

    # 2) violations（图片子集；[ABSENT]/<<<>>> 标记先剥离防自罚分）
    text = str(prompt)
    body_text = _strip_reference_markers(text)
    violations: dict[str, int] = {}
    excluded = meta.get("excluded_characters") or []
    if excluded:
        hit = [e for e in excluded if _contains_word(body_text, e)]
        if hit:
            violations["excluded_present"] = -10
            checks["excluded_hits"] = hit
    pairs = meta.get("no_swap_pairs") or []
    if pairs:
        hit = []
        for p in pairs:
            if isinstance(p, dict):
                from_name = p.get("from")
            elif isinstance(p, (list, tuple)) and len(p) == 2:
                from_name = p[0]
            else:
                continue
            if _contains_word(body_text, from_name):
                hit.append(p)
        if hit:
            violations["swap_source_present"] = -10
            checks["swap_hits"] = hit
    checks["violations"] = violations

    # 3) 六要素（与视频引擎共享 prompt_engine_core/knowledge/element_keywords.json；任一语言命中即算）
    lower = str(prompt).lower()
    element_keywords, _kw_from_asset = load_element_keywords()
    elements = {k: any(w in lower for _lst in v.values() for w in _lst) for k, v in element_keywords.items()}
    checks["elements"] = elements
    checks["elements_score"] = sum(elements.values()) / len(elements)

    # 4) 源保真（source 实体命中）
    fidelity = 1.0
    if source_prompt:
        zh_chars = re.findall(r"[\u4e00-\u9fff]{2,}", source_prompt)
        if zh_chars:
            hit = sum(1 for c in zh_chars[:8] if c in str(prompt))
            fidelity = max(0.0, hit / min(8, len(zh_chars)))
    checks["fidelity"] = fidelity

    score = (checks["length"] * 20 + checks["elements_score"] * 30 + fidelity * 20) / 0.7
    score += sum(violations.values())
    return {
        "score": round(max(0, min(100, score)), 1),
        "checks": checks,
        "tier": tier,
        "violations": violations,
    }


def select_best(
    candidates: list[tuple[str, dict]],
    source_prompt: str = "",
    language: str = "en",
    tier: str | None = None,
    max_length: int | None = None,
) -> tuple[str, dict, float]:
    """多候选择优：返回 (prompt, meta, score)，分数最高者优先（签名与视频引擎一致）。"""
    best: tuple[str, dict, float] | None = None
    for prompt, meta in candidates:
        info = evaluate_quality(
            prompt, meta, source_prompt=source_prompt, language=language,
            tier=tier, max_length=max_length,
        )
        score = float(info["score"])
        if best is None or score > best[2]:
            best = (prompt, meta, score)
    if best is None:
        return "", {}, 0.0
    return best
