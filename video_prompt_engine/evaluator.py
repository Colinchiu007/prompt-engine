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


def _parse_time_span(value: str) -> list[float] | None:
    """解析时间区间 "m:ss-m:ss" / "s.s-s.s"，返回 [start, end] 秒；解析失败返回 None。"""
    if not value:
        return None
    parts = str(value).split("-")
    if len(parts) != 2:
        return None

    def _to_seconds(token: str) -> float | None:
        token = token.strip()
        if not token:
            return None
        if ":" in token:
            m, _, sec = token.partition(":")
            try:
                return int(m) * 60 + float(sec)
            except (TypeError, ValueError):
                return None
        try:
            return float(token)
        except (TypeError, ValueError):
            return None

    start = _to_seconds(parts[0])
    end = _to_seconds(parts[1])
    if start is None or end is None:
        return None
    return [start, end]


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
    - refined：en 下界自适应（≤min(500, budget//6)）~ 5000 词（DEEP P0-1 词数刻度；max_length 是字符裁剪预算不参与上界判据）/ zh 500 字符至 max_length
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
            # DEEP P0-1：精修层 500-5,000 词（词数刻度）。max_length 为字符裁剪预算（optimizer 先裁后评），
            # 不参与 refined 上界判据——此前 upper=max(500, budget//5)=1000 词把 1000+ 词模板硬扣。
            # 下界保持自适应（评审 C1）：小预算（如 1800 字符 ≈360 词）下固定 500 词会误杀裁后结果，
            # min(500, max(150, budget//6)) 防区间坍缩（与旧 W4 下界语义一致）
            lower = min(500, max(150, (max_length or 5000) // 6))
            length_ok = lower <= words <= 5000
        else:
            # W4：batch 上界与 max_length 联动（默认 1800 → 400 零回归；大预算下消除 401+ 词死区）
            # W3 封顶 833（=5000//6）：le 上浮到 20000 后不随预算静默扩到 3333（batch 定位短小精炼，150-300 词）
            upper = min(max(400, (max_length or 1800) // 6), 833)
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
    audio_layers = (video or {}).get("audio_layers")
    if tier == "refined" and isinstance(audio_layers, dict):
        # REQ-3.4 判定表仅 refined 生效（Audio 段真实渲染进尾行）；batch 无尾行，仍走正文音频词检查，
        # 否则 batch 带 audio_layers 而正文无音频词会假阴性（评审 W1）
        has_audio = bool(str(audio_layers.get("sfx") or "").strip()) or bool(
            str(audio_layers.get("dialogue") or "").strip()
        )
    elif tier == "refined":
        has_audio = bool(audio_field) or any(k in lower_text for k in ("sfx", "sound", "audio", "music", "score"))
    else:
        if any(k in lower_text for k in ("silent", "no sound", "无声", "静音")):
            has_audio = False
        else:
            has_audio = any(k in lower_text for k in ("sfx", "sound", "audio", "music", "score", "音效", "配乐", "声音", "旋律"))
    if not has_audio:
        violations["missing_audio"] = -5

    # 6) Round3 Batch A T2 — 确定性 FAIL CHECK（纯结构/数学判定，无 LLM）：
    # timeline_missing：shots≥2 时正文（标记区剥离后）缺 [SHOT N]/[HARD CUT] 切分标记 → -5
    # timing_break：shots≥2 时 beats[].time 区间端点最大值超出 shot.duration+2s 容差 → -5
    shots = (video or {}).get("shots") or []
    if isinstance(shots, list) and len(shots) >= 2:
        # 引用协议标记区已剥离（<<<...>>>/[ABSENT] 内嵌的 [SHOT 不计数，评审 I1）；真实切分标记保留
        body_upper = body_text.upper()
        timeline_hits = ("[SHOT" in body_upper) or ("[HARD CUT" in body_upper)
        checks["timeline_hits"] = timeline_hits
        if not timeline_hits:
            violations["timeline_missing"] = -5

        timing_diff = None
        for shot in shots:
            if not isinstance(shot, dict):
                continue
            duration = shot.get("duration")
            beats = shot.get("beats") or []
            if not isinstance(beats, list):
                continue
            for beat in beats:
                if not isinstance(beat, dict):
                    continue
                time_span = str(beat.get("time") or "").strip()
                parsed = _parse_time_span(time_span)
                if parsed is None:
                    continue
                end_seconds = max(parsed)
                try:
                    duration_f = float(duration) if duration is not None and str(duration).strip() != "" else 0.0
                except (TypeError, ValueError):
                    continue
                diff = end_seconds - (duration_f + 2.0)
                if timing_diff is None or diff > timing_diff:
                    timing_diff = diff
                if diff > 0:
                    violations["timing_break"] = -5
        checks["timing_diff"] = round(timing_diff, 2) if timing_diff is not None else None
    else:
        checks["timeline_hits"] = None
        checks["timing_diff"] = None
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
