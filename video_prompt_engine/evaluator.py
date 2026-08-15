"""视频提示词质量评估 — 保真/六要素/镜头字段/长度（用于多候选择优与反馈评分）。"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

from video_prompt_engine.refined_blocks import clean_blocks, rendered_block_names

# Round3 Batch C：lock-gated 规则资产缓存（refined_blocks.json，缺失/损坏回退空表 → 规则不启用零误报）
_GATED_RULES_CACHE: dict = {}


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


def _strip_reference_markers(text: str, reference_names: list[str] | None = None) -> str:
    """剥离引用协议标记区段（[ABSENT] <name> / <<<...>>>），避免合规标记自罚分。

    契约侧 _assertReferenceProtocol 要求声明禁止项时正文嵌入标记；标记本身含角色名，
    计入 excluded/swap 命中会把引擎自己的合规输出判为违规。仅剥离标记 token 本身（+紧跟一个名字 token），
    标记后的同句真实出现仍会命中（评审 C1：过度剥离会隐藏真实违规）。
    """
    import re
    stripped = str(text or "")
    # 闭合 <<<...>>> 整段；未闭合前缀只按已知引用名精确剥离，避免中文无空格正文被 \S+ 吞掉。
    stripped = re.sub(r"<<<.*?>>>", "", stripped, flags=re.DOTALL)
    names = sorted(
        {str(name).strip() for name in (reference_names or []) if str(name or "").strip()},
        key=len,
        reverse=True,
    )
    for name in names:
        suffix = r"(?![A-Za-z0-9])" if re.search(r"[A-Za-z0-9]$", name) else ""
        stripped = re.sub(r"<<<\s*" + re.escape(name) + suffix, "", stripped, flags=re.IGNORECASE)
        stripped = re.sub(
            r"\[ABSENT\]\s*" + re.escape(name) + suffix,
            "",
            stripped,
            flags=re.IGNORECASE,
        )
    stripped = re.sub(r"<<<", "", stripped)
    stripped = re.sub(r"\[ABSENT\]", "", stripped, flags=re.IGNORECASE)
    return stripped.strip()


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


# Round3 Batch B：承接保真检查词表
# 停用词（功能词）与高频泛词（镜头/环境/画面无关词）分列——泛词残留会稀释命中率，
# 角色/姿势实体被丢仍 ≥60% 假阴性（评审 Warning-3）。
_CONTINUITY_STOPWORDS = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "and", "or", "but", "of", "in", "on", "at", "to", "for", "with", "by",
    "from", "as", "his", "her", "its", "their", "they", "he", "she", "it",
    "we", "you", "i", "that", "this", "these", "those", "there", "here",
    "not", "no", "all", "each", "both", "into", "onto", "over", "under",
    "between", "toward", "towards", "around", "across", "against", "during",
    "through", "before", "after", "above", "below", "out", "up", "down",
    "off", "away", "near", "far", "also", "very", "then", "than", "when",
    "while", "which", "who", "whom", "what", "where", "how", "why",
    "has", "have", "had", "will", "would", "shall", "should", "can", "could",
    "may", "might", "must", "do", "does", "did", "just", "only", "even",
    "still", "yet", "now", "once", "much", "many", "more", "most", "some",
    "any", "such", "same", "other", "another", "one", "two", "three",
    "first", "second", "third", "last", "next", "back",
})
_CONTINUITY_GENERIC = frozenset({
    "camera", "frame", "frames", "screen", "shot", "shots", "scene", "view",
    "angle", "lens", "cut", "cuts", "fade", "focus", "center", "middle",
    "edge", "light", "lighting", "shadow", "shadowing", "background",
    "foreground", "atmosphere", "tone", "palette", "texture", "surface",
    "space", "position", "positioned", "motion", "movement", "style", "look",
    "detail", "details", "slow", "fast", "left", "right", "top", "bottom",
    "front", "rear", "side", "area", "region", "part", "full", "half",
    "wide", "low", "high", "dark", "bright", "soft", "hard", "cold", "warm",
})
# 中文位置/姿势关键词表（白名单判定用；显式词表而非 2-gram——评审 Critical-1）
_CONTINUITY_ZH_POSTURE = (
    "站起", "站立", "坐下", "躺着", "跪着", "趴着", "倒下", "低头", "抬头",
    "转身", "面向", "背对", "闭眼", "睁眼", "流血", "握着", "举起", "抱住",
    "靠着", "昏迷", "死亡", "地上", "雪地", "门口", "角落", "中央", "前景",
    "背景", "远处", "墙边", "窗边", "边缘", "水面", "台阶", "床边", "树下",
)

# 否定感知（评审 Critical-2/C3）：forbidden 命中前查否定前缀，禁令形态不计命中。
# 扩充：out of / away from / free of / devoid of / nobody / no one / do not / don't / absent（评审补充），
# 覆盖三分法/视线约束的自然禁令措辞（"keep the hero OUT of the center of frame"、"nobody is looking at camera"）。
_NEGATION_RE = re.compile(
    r"(?i)(?:\b(?:no|not|without|never|avoid|nobody|no one|do not|don't|out of|away from|free of|devoid of|absent)\b(?:\s+\S+){0,4}\s*"
    r"|(?:无|不|禁止|切勿|避免)[^，。！？；,;.!?\n]{0,16})$"
)


def _token_occurrences(text: str, token: str) -> tuple[str, list[re.Match]]:
    token = str(token or "").strip()
    if not token or len(token) < 2:
        return str(text or ""), []
    text_value = str(text or "")
    pattern = re.compile(
        r"(?<![A-Za-z0-9])" + re.escape(token) + r"(?![A-Za-z0-9])",
        flags=re.IGNORECASE,
    )
    return text_value, list(pattern.finditer(text_value))


def _occurrence_is_negated(text_value: str, match: re.Match) -> bool:
    prefix = text_value[max(0, match.start() - 64):match.start()]
    clause_prefix = re.split(r"[，。！？；,;.!?\n]", prefix)[-1]
    return _NEGATION_RE.search(clause_prefix) is not None


def _count_negated_occurrences(text: str, token: str) -> int:
    """Count token occurrences negated in their own clause."""
    text_value, matches = _token_occurrences(text, token)
    return sum(1 for match in matches if _occurrence_is_negated(text_value, match))


def _negated(text: str, token: str) -> bool:
    """仅当 token 的每一次出现都在各自分句内被否定时返回 True。"""
    text_value, matches = _token_occurrences(text, token)
    if not matches:
        return False
    return all(_occurrence_is_negated(text_value, match) for match in matches)


def _extract_continuity_tokens(text: str) -> list[str]:
    """英文实体 token 提取：≥2 字符字母数字（连字符/撇号保留），去停用词与高频泛词，去重保序。"""
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9'\-]{1,}", str(text or ""))
    seen: set[str] = set()
    result: list[str] = []
    for t in tokens:
        low = t.lower()
        if low in _CONTINUITY_STOPWORDS or low in _CONTINUITY_GENERIC:
            continue
        if low not in seen:
            seen.add(low)
            result.append(low)
    return result


def _check_continuity(prompt: str, prev_final_frame: str, character_list: list) -> tuple[bool, dict]:
    """跨镜承接保真（Round3 Batch B，评审修订版）。

    英文：实体 token 命中率 ≥40%，且终态帧中实际出现的角色名必中（硬判据，评审 W1 收窄——
    全量场景 roster 不要求全部出镜，只约束上一镜终态确实在场的主体）。
    中文：弃 2-gram——显式白名单（角色名 + 终态中出现的姿势/位置词）命中 ≥60%；
          无白名单时终态文本在 body 中的最长匹配覆盖率（find_longest_match 块长 / 终态长）≥0.5
          （评审 Critical-1：旧 SequenceMatcher 整句 ratio 在生产长度下数学不可达——500+ 字符 body
          逐字重述 50 字符终态也只有 ~0.18；覆盖率口径下完整重述 ≈1.0 可判定）。
    返回 (通过?, checks)。无 prev_final_frame 时通过且 ratio=None（零回归）。
    """
    if not prev_final_frame:
        return True, {"continuity_hits": 0, "continuity_total": 0, "continuity_ratio": None, "continuity_method": None}
    body = _strip_reference_markers(prompt)
    roster = [str(n).strip() for n in (character_list or []) if str(n or "").strip()]
    # 评审 W1：硬判据只针对"终态帧中实际出现的角色"，未入终态的副角色不要求出镜
    names = [n for n in roster if _contains_word(prev_final_frame, n)]
    is_zh = bool(re.search(r"[\u4e00-\u9fff]", str(prev_final_frame)))
    if is_zh:
        keywords = [w for w in _CONTINUITY_ZH_POSTURE if w in prev_final_frame]
        whitelist = names + keywords
        if whitelist:
            hits = []
            for w in whitelist:
                if len(w) >= 2:
                    if _contains_word(body, w):
                        hits.append(w)
                elif w in body:
                    hits.append(w)
            ratio = len(hits) / len(whitelist)
            ok = ratio >= 0.6
            return ok, {
                "continuity_hits": len(hits), "continuity_total": len(whitelist),
                "continuity_ratio": round(ratio, 3), "continuity_method": "whitelist",
            }
        sm = SequenceMatcher(None, prev_final_frame, body)
        match = sm.find_longest_match(0, len(prev_final_frame), 0, len(body))
        ratio = (match.size / len(prev_final_frame)) if prev_final_frame else 1.0
        ok = ratio >= 0.5
        return ok, {
            "continuity_hits": round(ratio, 3), "continuity_total": 1,
            "continuity_ratio": round(ratio, 3), "continuity_method": "ratio",
        }
    tokens = _extract_continuity_tokens(prev_final_frame)
    hits = [t for t in tokens if _contains_word(body, t)]
    ratio = len(hits) / len(tokens) if tokens else 1.0
    checks = {
        "continuity_hits": len(hits), "continuity_total": len(tokens),
        "continuity_ratio": round(ratio, 3), "continuity_method": "wordlist",
    }
    ok = ratio >= 0.4
    if names:
        missing = [n for n in names if not _contains_word(body, n)]
        if missing:
            ok = False
            checks["continuity_missing"] = missing
    return ok, checks


def _gated_rules() -> dict:
    """加载 refined_blocks.json lock_triggers/enabled_rules（缓存；缺失/损坏回退空表 → 规则不启用）。"""
    if not _GATED_RULES_CACHE:
        try:
            from pathlib import Path
            import json
            p = Path(__file__).resolve().parent / "knowledge" / "refined_blocks.json"
            if p.exists():
                data = json.loads(p.read_text(encoding="utf-8"))
                _GATED_RULES_CACHE["triggers"] = data.get("lock_triggers") or {}
                _GATED_RULES_CACHE["enabled"] = set(data.get("enabled_rules") or [])
                _GATED_RULES_CACHE["coverage"] = data.get("coverage") or {}
            else:
                _GATED_RULES_CACHE["triggers"] = {}
                _GATED_RULES_CACHE["enabled"] = set()
                _GATED_RULES_CACHE["coverage"] = {}
        except Exception:
            _GATED_RULES_CACHE["triggers"] = {}
            _GATED_RULES_CACHE["enabled"] = set()
            _GATED_RULES_CACHE["coverage"] = {}
    return _GATED_RULES_CACHE


def _apply_gated_rules(prompt: str, tier: str, violations: dict, checks: dict) -> None:
    """lock-gated 启发式（Round3 Batch C）：refined 专属；enabled_rules 控制启用；
    仅声明 lock 词时检测 forbidden（否定感知），命中 -5 advisory。"""
    if tier != "refined":
        checks["gated_hits"] = []
        return
    rules = _gated_rules()
    triggers = rules.get("triggers") or {}
    enabled = rules.get("enabled") or set()
    body = _strip_reference_markers(prompt)
    hits: list[str] = []
    for name, rule in triggers.items():
        if name not in enabled:
            continue
        locks = rule.get("locks") or []
        forbidden = rule.get("forbidden") or []
        if not locks or not forbidden:
            continue
        if not any(_contains_word(body, l) and not _negated(body, l) for l in locks):
            continue
        for f in forbidden:
            if _contains_word(body, f) and not _negated(body, f):
                violations[name] = -5
                hits.append(name)
                break
    checks["gated_hits"] = hits


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
    prev_final_frame: str | None = None,
    character_list: list | None = None,
) -> dict:
    """返回 {score: 0-100, checks: {...}, tier, violations}。

    tier 层级（Higgsfield P0）：
    - batch：en 100-400 词 / zh 120-2000 字符
    - refined：en 下界自适应（≤min(500, budget//6)）~ 5000 词（DEEP P0-1 词数刻度；max_length 是字符裁剪预算不参与上界判据）/ zh 500 字符至 max_length
    violations：缺席角色 -10 / swap 被替换 -10 / refined 缺尾行 -10 / 缺 Audio 块 -5 /
    continuity_break -5（跨镜承接，评审修订版实体级算法）/ block_coverage -5（refined 块覆盖，自渲染口径）/
    lock-gated 规则 -5（否定感知，默认 3 条启用）。
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
    violations: dict[str, int] = {}
    excluded = (video or {}).get("excluded_characters") or []
    pairs = (video or {}).get("no_swap_pairs") or []
    reference_names = [str(item).strip() for item in excluded if str(item or "").strip()]
    for pair in pairs:
        if isinstance(pair, dict):
            pair_names = (pair.get("from"), pair.get("to"))
        elif isinstance(pair, (list, tuple)) and len(pair) == 2:
            pair_names = pair
        else:
            continue
        reference_names.extend(str(item).strip() for item in pair_names if str(item or "").strip())
    body_text = _strip_reference_markers(text, reference_names)
    if excluded:
        hit = [e for e in excluded if _contains_word(body_text, e)]
        if hit:
            violations["excluded_present"] = -10
            checks["excluded_hits"] = hit
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
        has_audio = any(
            bool(str(audio_layers.get(key) or "").strip())
            for key in ("environment", "sfx", "dialogue")
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

    # 7) Round3 Batch B — 跨镜承接保真（实体级；引用标记剥离后判定；无 prev_final_frame 跳过零回归）
    if prev_final_frame:
        continuity_ok, continuity_checks = _check_continuity(prompt, prev_final_frame, character_list or [])
        checks.update(continuity_checks)
        if not continuity_ok:
            violations["continuity_break"] = -5
    else:
        checks.update({
            "continuity_hits": 0, "continuity_total": 0,
            "continuity_ratio": None, "continuity_method": None,
        })

    # 8) Round3 Batch C — 块覆盖度（refined 专属，引擎自渲染口径）
    # 分母 = meta.blocks 非空块数，分子 = 渲染串中命中块标记数（统一正则，行首标题+冒号）；
    # 与语料分族统计解耦（评审 Critical-2：语料众数 8/12 卡阈值必误报）。
    blocks = clean_blocks((video or {}).get("blocks"))
    if tier == "refined" and blocks:
        non_empty = list(blocks)
        if non_empty:
            rendered_names = rendered_block_names(prompt)
            hits = sum(1 for k in non_empty if k in rendered_names)
            ratio = hits / len(non_empty)
            checks["block_coverage"] = {"hit": hits, "total": len(non_empty), "ratio": round(ratio, 3)}
            min_ratio = float((_gated_rules().get("coverage") or {}).get("min_ratio", 0.8))
            if ratio < min_ratio:
                violations["block_coverage"] = -5
        else:
            checks["block_coverage"] = None
    else:
        checks["block_coverage"] = None

    # 9) Round3 Batch C — lock-gated 启发式（否定感知；enabled_rules 默认 3 条；batch 不启用）
    _apply_gated_rules(prompt, tier, violations, checks)
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
    prev_final_frame: str | None = None,
    character_list: list | None = None,
) -> tuple[str, dict, float]:
    """多候选择优：返回 (prompt, video_meta, score)，分数最高者优先。"""
    best: tuple[str, dict, float] | None = None
    for prompt, meta in candidates:
        info = evaluate(
            prompt, meta, source_prompt=source_prompt, language=language, tier=tier,
            max_length=max_length, prev_final_frame=prev_final_frame, character_list=character_list,
        )
        score = float(info["score"])
        if best is None or score > best[2]:
            best = (prompt, meta, score)
    if best is None:
        return "", {}, 0.0
    return best
