"""视频提示词质量评估 — 保真/六要素/镜头字段/长度（用于多候选择优与反馈评分）。"""
from __future__ import annotations

import re


def count_words(text: str) -> int:
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

    契约侧 _assertReferenceProtocol 要求声明禁止项时正文嵌入标记；标记本身含角色名，
    计入 excluded/swap 命中会把引擎自己的合规输出判为违规。仅剥离标记 token 本身（+紧跟一个名字 token），
    标记后的同句真实出现仍会命中（评审 C1：过度剥离会隐藏真实违规）。
    """
    import re
    stripped = str(text or "")
    # 闭合 <<<...>>> 整段；未闭合的 <<< 前缀只剥标记 + 紧邻一个词（契约仅要求 includes('<<<')，不要求闭合）
    stripped = re.sub(r"<<<.*?>>>", "", stripped, flags=re.DOTALL)
    stripped = re.sub(r"<<<\s*\S+", "", stripped)
    # [ABSENT] <name>：只剥标记与紧邻的一个词（中文无空格整段亦可），保留后续正文
    stripped = re.sub(r"\[ABSENT\]\s*\S+", "", stripped, flags=re.IGNORECASE)
    return stripped


def detect_tier(prompt: str, video: dict | None, explicit_tier: str | None = None) -> str:
    """tier 判定：explicit（optimizer 按 creative_level≥7 传入 refined，否则 batch）优先；无 explicit 时 auto-detect 兜底。

    自动判据：shots 非空 / prompt 含 NON-IP 或 FINAL FRAME（refined 输出特征）。
    """
    if explicit_tier in ("refined", "batch"):
        return explicit_tier
    upper = str(prompt or "").upper()
    if (video and video.get("shots")) or "NON-IP" in upper or "FINAL FRAME" in upper:
        return "refined"
    return "batch"


def evaluate(
    prompt: str,
    video: dict | None,
    source_prompt: str = "",
    language: str = "en",
    tier: str | None = None,
    max_length: int | None = None,
) -> dict:
    """返回 {score: 0-100, checks: {...}, tier, violations}。

    tier 层级（Higgsfield P0）：
    - batch：en 100-400 词 / zh 120-2000 字符
    - refined：en min(500, max(150, max_length//6)) ~ max(500, max_length//5) 词（下界随预算缩放防坍缩）/ zh 500 字符至 max_length（≤5000）
    violations：缺席角色 -10 / swap 被替换 -10 / refined 缺尾行 -10 / 缺 Audio 块 -5。
    """
    checks = {}
    tier = detect_tier(prompt, video, explicit_tier=tier)
    checks["tier"] = tier

    # 1) 长度层级（batch/refined 分开，refined 上界与 max_length 联动避免死代码）
    words = count_words(prompt)
    if language == "zh":
        if tier == "refined":
            length_ok = 500 <= len(str(prompt)) <= (max_length or 5000)
        else:
            length_ok = 120 <= len(str(prompt)) <= 2000
    else:
        if tier == "refined":
            # 下界随预算缩放：小预算（如 1800 字符 ≈300 词）下 500 词不可达，min(500, max(150, budget//6)) 防区间坍缩
            lower = min(500, max(150, (max_length or 5000) // 6))
            upper = max(500, (max_length or 5000) // 5)
            length_ok = lower <= words <= upper
        else:
            # W4：batch 上界与 max_length 联动（默认 1800 → 400 零回归；大预算下消除 401+ 词死区）
            upper = max(400, (max_length or 1800) // 6)
            length_ok = 100 <= words <= upper
    checks["length"] = length_ok
    checks["words"] = words

    # 5) Higgsfield violations（词边界/整名匹配，字段为空时 N/A 不误扣；[ABSENT]/<<<>>> 标记区段先剥离防自罚分）
    text = str(prompt)
    upper_text = text.upper()
    body_text = _strip_reference_markers(text)
    violations: dict[str, int] = {}
    excluded = (video or {}).get("excluded_characters") or []
    if excluded:
        hit = [e for e in excluded if _contains_word(body_text, e)]
        if hit:
            violations["excluded_present"] = -10
            checks["excluded_hits"] = hit
    pairs = (video or {}).get("no_swap_pairs") or []
    if pairs:
        # 双形态兼容：契约规范形态二元组 [from, to] 与引擎对象形态 {from,to} 均读 from 侧；非法形态跳过防 AttributeError
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
    if tier == "refined" and "NON-IP" not in upper_text:
        violations["missing_trailer"] = -10
    lower_text = text.lower()
    # 缺 Audio 块：refined 尾行自带 `{audio} only.`（meta.audio 非空即满足）；batch 检查正文音频词（否定词优先）
    audio_field = str((video or {}).get("audio") or "").strip()
    if tier == "refined":
        has_audio = bool(audio_field) or any(k in lower_text for k in ("sfx", "sound", "audio", "music", "score"))
    else:
        if any(k in lower_text for k in ("silent", "no sound", "无声", "静音")):
            has_audio = False
        else:
            has_audio = any(k in lower_text for k in ("sfx", "sound", "audio", "music", "score", "音效", "配乐", "声音", "旋律"))
    if not has_audio:
        violations["missing_audio"] = -5
    checks["violations"] = violations

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
    """多候选择优：返回 (prompt, video_meta, score)，分数最高者优先。"""
    best: tuple[str, dict, float] | None = None
    for prompt, meta in candidates:
        info = evaluate(prompt, meta, source_prompt=source_prompt, language=language, tier=tier, max_length=max_length)
        score = float(info["score"])
        if best is None or score > best[2]:
            best = (prompt, meta, score)
    if best is None:
        return "", {}, 0.0
    return best
