"""视频提示词质量评估 — 保真/六要素/镜头字段/长度（用于多候选择优与反馈评分）。"""
from __future__ import annotations

import re


def count_words(text: str) -> int:
    return len(str(text or "").split())


def evaluate(prompt: str, video: dict | None, source_prompt: str = "", language: str = "en") -> dict:
    """返回 {score: 0-100, checks: {...}}。"""
    checks = {}

    # 1) 长度：专业 150-300 词
    words = count_words(prompt)
    if language == "zh":
        length_ok = 120 <= len(str(prompt)) <= 4000
    else:
        length_ok = 100 <= words <= 400
    checks["length"] = length_ok
    checks["words"] = words

    # 2) 六要素（英文关键词）
    lower = str(prompt).lower()
    elements = {
        "subject": any(k in lower for k in ("character", "subject", "hero", "woman", "man", "general", "people", "person", "warrior", "soldier", "horse", "cat", "dog", "人", "将军", "女子", "士兵", "战士", "主角")),
        "action": any(k in lower for k in ("running", "walking", "riding", "fighting", "motion", "moving", "move", "runs", "rushing", "chasing", "flying", "dancing", "walk", "飞", "奔", "战", "走", "跑", "追", "舞", "骑")),
        "environment": any(k in lower for k in ("environment", "scene", "background", "landscape", "city", "室", "城", "原野", "景")),
        "lighting": any(k in lower for k in ("light", "lighting", "sunlight", "golden hour", "光")),
        "color": any(k in lower for k in ("color", "palette", "hue", "色")),
        "style": any(k in lower for k in ("style", "cinematic", "epic", "style", "风格")),
    }
    checks["elements"] = elements
    checks["elements_score"] = sum(elements.values()) / len(elements)

    # 3) 镜头字段（结构化 video）
    checks["has_shot"] = bool(video and video.get("shot"))
    checks["has_camera"] = bool(video and video.get("camera"))
    checks["has_motion"] = bool(video and video.get("motion_intensity"))

    # 4) 保真（source 实体命中，粗略）
    fidelity = 1.0
    if source_prompt:
        zh_chars = re.findall(r"[\u4e00-\u9fff]{2,}", source_prompt)
        if zh_chars:
            hit = sum(1 for c in zh_chars[:8] if c in str(prompt))
            fidelity = max(0.0, hit / min(8, len(zh_chars)))
    checks["fidelity"] = fidelity

    score = (
        (checks["length"] * 20)
        + (checks["elements_score"] * 30)
        + (20 if checks["has_shot"] else 0)
        + (15 if checks["has_camera"] else 0)
        + (15 if checks["has_motion"] else 0)
        + (fidelity * 20)
    ) / 1.2
    return {"score": round(max(0, min(100, score)), 1), "checks": checks}


def select_best(
    candidates: list[tuple[str, dict]],
    source_prompt: str = "",
    language: str = "en",
) -> tuple[str, dict, float]:
    """多候选择优：返回 (prompt, video_meta, score)，分数最高者优先。"""
    best: tuple[str, dict, float] | None = None
    for prompt, meta in candidates:
        info = evaluate(prompt, meta, source_prompt=source_prompt, language=language)
        score = float(info["score"])
        if best is None or score > best[2]:
            best = (prompt, meta, score)
    if best is None:
        return "", {}, 0.0
    return best
