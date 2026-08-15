"""视频提示词质量评估 — 保真/六要素/镜头字段/长度（用于多候选择优与反馈评分）。"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

from video_prompt_engine.refined_blocks import clean_blocks, rendered_block_names
from prompt_engine_core.knowledge import load_element_keywords

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


def _stem_en(token: str) -> str:
    """轻量英文词干（仅保真命中用，保守优先：只做低风险归并，防不同词根撞干）。

    复数 -s/-es（es 仅 sibilant 词尾）、双写辅音的 -ing/-ed 归并；
    e-dropping（stare→stared）、不规则词与长度 ≤3 词不归并——宁可假阴性，
    不做 stares→star / hated→hat 类撞干（评审复验 W3-新）。
    """
    t = str(token or "").lower()
    if len(t) <= 3:
        return t
    if t.endswith(("sses", "shes", "ches", "xes", "zes")):
        t = t[:-2]
    elif t.endswith("s") and not t.endswith("ss") and not t.endswith("us"):
        t = t[:-1]
    for suffix in ("ing", "ed"):
        if t.endswith(suffix) and len(t) - len(suffix) >= 4:
            stem = t[:-len(suffix)]
            if len(stem) >= 4 and stem[-1] == stem[-2]:
                t = stem[:-1]
            break
    return t


def _en_stems(text: str) -> set[str]:
    """文本全部英文 token 的词干集合（保真词形归一命中用）。"""
    return {_stem_en(t) for t in re.findall(r"[a-z][a-z0-9'\-]{1,}", str(text or "").lower())}


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

    自动判据：shots 非空 / prompt 含 NON-IP 或 FINAL FRAME（refined 输出特征）；
    P0-1 长度兜底：无引擎标记且 >833 词 → refined（真实语料多无标记，旧判据 70/258 误分层）。
    语言限制（W11）：count_words 按空格切分，无空格中文不走长度兜底（中文精修通常带标记或显式 tier）。
    """
    if explicit_tier in ("refined", "batch", "asset", "variant"):
        return explicit_tier
    upper = str(prompt or "").upper()
    if (video and video.get("shots")) or "NON-IP" in upper or "FINAL FRAME" in upper:
        return "refined"
    if count_words(prompt) > 833:
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
    length_strict: bool = True,
    enable_advice: bool = True,
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

    # 1) 长度层级（batch/refined/asset/variant 分带；P2-1 asset/variant 语料形态层）
    words = count_words(prompt)
    measure = len(str(prompt)) if language == "zh" else words
    # form 形态标签：显式 tier=asset/variant，或短卡（<100 词/字）推断为 asset；其余 regular
    # （评审复验 W1-新：中文无空格 count_words≈1，必须用 measure（zh=字符数）判定，否则整语言误判 asset）
    if tier in ("asset", "variant"):
        form = tier
    elif measure < 100:
        form = "asset"
    else:
        form = "regular"
    checks["form"] = form
    if language == "zh":
        if tier == "refined":
            lo, hi = 500, (max_length or 5000)
        elif tier == "asset":
            lo, hi = 40, 1900
        elif tier == "variant":
            lo, hi = 80, 2000
        else:
            lo, hi = 120, 2000
    else:
        if tier == "refined":
            # DEEP P0-1：精修层 500-5,000 词（词数刻度）。max_length 为字符裁剪预算（optimizer 先裁后评），
            # 不参与 refined 上界判据。下界保持自适应（评审 C1）：min(500, max(150, budget//6)) 防区间坍缩
            lo = min(500, max(150, (max_length or 5000) // 6))
            hi = 5000
        elif tier == "asset":
            lo, hi = 20, 950
        elif tier == "variant":
            hi = min(max(400, (max_length or 1800) // 6), 833)
            lo, hi = 50, hi
        else:
            # W4：batch 上界与 max_length 联动（默认 1800 → 400 零回归）；W3 封顶 833
            hi = min(max(400, (max_length or 1800) // 6), 833)
            lo, hi = 100, hi
    length_ok = lo <= measure <= hi
    checks["length"] = length_ok
    checks["words"] = words
    checks["length_band"] = [lo, hi]
    # P1-2 长度梯度：length_strict=False（评测口径）按接近度 0-20；True（引擎候选口径）0/20 二值
    if length_strict:
        length_points = 20 if length_ok else 0
    else:
        bandwidth = max(1, hi - lo)
        if length_ok:
            length_points = 20.0
        else:
            dist = min(abs(measure - lo), abs(measure - hi))
            length_points = round(20.0 * max(0.0, 1.0 - dist / bandwidth), 1)
    checks["length_points"] = length_points

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
        # 质量评估 P1-2：真实精修语料以控制段（Duration/Aspect/连续长镜头/分镜标记/终态块）等价表达 trailer
        # 预期，识别控制段形态即视为有 trailer 预期，不强制 NON-IP 字面量（引擎自产尾行仍为 NON-IP，不受影响）
        _TRAILER_EQUIV = (
            "DURATION:", "ASPECT RATIO", "ASPECT:", "ONE CONTINUOUS SHOT",
            "CUT 1", "CUT 2", "[SHOT", "FINAL FRAME", "STILLNESS LOCK", "SCENE NOTE",
        )
        if not any(k in upper_text for k in _TRAILER_EQUIV):
            violations["missing_trailer"] = -10
    lower_text = text.lower()
    # 缺 Audio 块：refined 尾行自带 `{audio} only.`（meta.audio 非空即满足）；batch 层改为「显式音频需求」判定——
    # 仅当正文含音频意图词或 meta 显式声明音频时才要求音频词；纯视觉/静态形态默认 N/A 不扣分（质量评估 P1-1 修复）
    _SILENCE_WORDS = ("silent", "no sound", "无声", "静音", "无音效")
    _AUDIO_INTENT_WORDS = (
        "sfx", "sound effects", "sound design", "soundscape", "ambient audio",
        "audio cue", "diegetic", "music", "score", "dialogue", "vocal",
        "voiceover", "narration", "音效", "配乐", "声音", "对话", "旁白", "音轨", "音频",
    )
    audio_field = str((video or {}).get("audio") or "").strip()
    audio_layers = (video or {}).get("audio_layers")
    if tier == "refined" and isinstance(audio_layers, dict):
        # REQ-3.4 判定表仅 refined 生效（Audio 段真实渲染进尾行）；batch 无尾行，走正文音频词检查，
        # 否则 batch 带 audio_layers 而正文无音频词会假阴性（评审 W1）
        has_audio = any(
            bool(str(audio_layers.get(key) or "").strip())
            for key in ("environment", "sfx", "dialogue")
        )
    elif tier == "refined":
        has_audio = bool(audio_field) or any(k in lower_text for k in ("sfx", "sound", "audio", "music", "score"))
    else:
        if any(k in lower_text for k in _SILENCE_WORDS):
            has_audio = False
        elif audio_field or any(k in lower_text for k in _AUDIO_INTENT_WORDS):
            has_audio = True
        else:
            has_audio = None  # 纯视觉/静态形态：无显式音频需求，N/A 不扣分
    if has_audio is False:
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

    # 2) 六要素（关键词资产 prompt_engine_core/knowledge/element_keywords.json，P1-4 外置；
    #    en/zh/ru 任一语言命中即算——P2-2 多语种；部分命中 score=min(1, 命中词数/3)——P1-1 区分度）
    lower = str(prompt).lower()
    elements_detail: dict = {}
    element_keywords, _kw_from_asset = load_element_keywords()
    for _elem, _langs in element_keywords.items():
        _toks = list(dict.fromkeys(w for _v in _langs.values() for w in _v))
        _hits = sorted({t for t in _toks if t in lower})
        elements_detail[_elem] = {
            "hit": bool(_hits), "words": _hits[:8], "score": round(min(1.0, len(_hits) / 3.0), 3),
        }
    elements = {k: v["hit"] for k, v in elements_detail.items()}
    checks["elements"] = elements
    checks["elements_detail"] = elements_detail
    checks["elements_score"] = round(sum(v["score"] for v in elements_detail.values()) / len(elements_detail), 3)

    # 3) 镜头字段（结构化 video；缺失时文本级兜底——质量评估 P0-1：纯文本评测不再被 58.3 硬顶）
    _TXT_SHOT = ("shot", "cut", "establishing", "close-up", "closeup", "wide", "overhead",
                 "tracking", "dolly", "zoom", "pan", "tilt", "slow-motion", "特写", "全景", "俯拍", "跟拍", "推移")
    _TXT_CAMERA = ("camera", "lens", "angle", "perspective", "viewpoint", "镜头", "机位", "视角", "广角", "长焦")
    # P0-4：运镜词表只保留镜头运动词（主体运动 walking/running/moving 不再计运镜）
    _TXT_MOTION = ("slow-motion", "pan", "tilt", "tracking", "dolly", "zoom", "crane", "handheld",
                   "drift", "swirl", "whip", "运镜", "摇镜", "推镜", "拉镜", "跟拍", "推移", "旋转", "慢动作")
    _has_txt = lambda toks: any(_contains_word(text, t) for t in toks)  # W4：词边界，子串兜底会误击 pandemic/companion(pan)
    checks["has_shot"] = bool(video and video.get("shot")) or _has_txt(_TXT_SHOT)
    checks["has_camera"] = bool(video and video.get("camera")) or _has_txt(_TXT_CAMERA)
    checks["has_motion"] = bool(video and video.get("motion_intensity")) or _has_txt(_TXT_MOTION)

    # 4) 保真（source 实体命中：中文 2-gram；英文实体 token 词边界命中——P0-3 英文保真补盲区）
    fidelity = 1.0
    if source_prompt:
        zh_chars = re.findall(r"[\u4e00-\u9fff]{2,}", source_prompt)
        if zh_chars:
            hit = sum(1 for c in zh_chars[:8] if c in str(prompt))
            fidelity = max(0.0, hit / min(8, len(zh_chars)))
        else:
            tokens = _extract_continuity_tokens(source_prompt)
            if tokens:
                # W3：词形归一（robot→robots/run→runs）——全词边界对复数/时态假阴性，保真路径轻量容忍
                prompt_stems = _en_stems(prompt)
                hits = [t for t in tokens if _contains_word(prompt, t) or _stem_en(t) in prompt_stems]
                fidelity = round(len(hits) / len(tokens), 3)
    checks["fidelity"] = fidelity

    score = (
        length_points
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
        "advice": _build_advice(prompt, checks, violations, language) if enable_advice else [],
    }


# P2-3：可解释建议（纯规则，中英双语按 language；enable_advice=False 关闭）——违规键 → (zh, en) 文案
_ADVICE_VIOLATION_TEXT = {
    "excluded_present": ("正文出现了禁止角色", "excluded character appears in body"),
    "swap_source_present": ("检测到需替换的角色源名", "swap source character name detected"),
    "missing_trailer": ("精修层缺少尾行/控制段（NON-IP 或 Duration/Cut 标记）", "refined prompt missing trailer/control block (NON-IP or Duration/Cut marker)"),
    "missing_audio": ("缺少音频描述（silent/无音效或显式音频意图）", "missing audio description (silent or explicit audio intent)"),
    "timeline_missing": ("多镜头未使用 [SHOT N]/[HARD CUT] 切分标记", "multi-shot prompt missing [SHOT N]/[HARD CUT] markers"),
    "timing_break": ("beats 时间超出 shot 时长容差", "beat timing exceeds shot duration tolerance"),
    "continuity_break": ("跨镜承接实体丢失", "continuity entities lost from previous frame"),
    "block_coverage": ("精修块覆盖不足", "refined block coverage below threshold"),
    "exposure_break": ("曝光一致性被破坏", "exposure consistency broken"),
    "silhouette_break": ("剪影一致性被破坏", "silhouette consistency broken"),
    "dead_center": ("主体被居中构图", "dead-center composition"),
    "warm_light_leak": ("出现暖光漏光", "warm light leak detected"),
    "style_contamination": ("风格污染", "style contamination"),
    "skin_guard": ("面部/皮肤细节失守", "face/skin detail guard failed"),
    "eye_line": ("视线未对镜头", "gaze not toward camera"),
}

# P2-3 补充：六要素中文标签（zh advice 可读性）
_ELEMENT_ZH_LABELS = {
    "subject": "主体", "action": "动作", "environment": "环境",
    "lighting": "光线", "color": "色彩", "style": "风格",
}


def _build_advice(prompt: str, checks: dict, violations: dict, language: str) -> list[str]:
    """纯规则建议生成：长度带外 + 缺失要素 + 镜头维度 + 违规逐条映射（zh 按 language 参数）。"""
    zh = str(language or "").lower().startswith("zh")
    advice: list[str] = []

    if not checks.get("length"):
        band = checks.get("length_band") or []
        words = checks.get("words") or 0
        measure = len(str(prompt)) if zh else words
        if len(band) == 2:
            lo, hi = band
            if zh:
                advice.append(f"长度 {measure} 字，建议带 {lo}-{hi}")
            else:
                advice.append(f"length {measure} words is outside suggested band {lo}-{hi}")

    for elem, detail in (checks.get("elements_detail") or {}).items():
        if not detail.get("score"):
            label = _ELEMENT_ZH_LABELS.get(elem, elem)
            advice.append(f"缺少要素：{label}" if zh else f"missing element: {label}")

    if not checks.get("has_shot"):
        advice.append("未检测到镜头/景别描述" if zh else "no shot/framing description detected")
    if not checks.get("has_camera"):
        advice.append("未检测到机位/视角描述" if zh else "no camera angle/viewpoint description detected")
    if not checks.get("has_motion"):
        advice.append("未检测到运镜描述" if zh else "no camera motion description detected")

    for key in (violations or {}):
        text = _ADVICE_VIOLATION_TEXT.get(key)
        if text:
            advice.append(text[0] if zh else text[1])
        else:
            advice.append(f"违反规则：{key}" if zh else f"rule violation: {key}")
    return advice


def select_best(
    candidates: list[tuple[str, dict]],
    source_prompt: str = "",
    language: str = "en",
    tier: str | None = None,
    max_length: int | None = None,
    prev_final_frame: str | None = None,
    character_list: list | None = None,
    length_strict: bool = True,
) -> tuple[str, dict, float]:
    """多候选择优：返回 (prompt, video_meta, score)，分数最高者优先；
    同分时违规数少者胜（P1-3 tie-break），仍同分取先出现者（稳定）。"""
    best: tuple[str, dict, float, int] | None = None
    for prompt, meta in candidates:
        info = evaluate(
            prompt, meta, source_prompt=source_prompt, language=language, tier=tier,
            max_length=max_length, prev_final_frame=prev_final_frame, character_list=character_list,
            length_strict=length_strict,
        )
        score = float(info["score"])
        n_violations = len(info.get("violations") or {})
        if best is None or score > best[2] or (score == best[2] and n_violations < best[3]):
            best = (prompt, meta, score, n_violations)
    if best is None:
        return "", {}, 0.0
    return best[0], best[1], best[2]

# video-corpus-expansion 组5：failure_patterns.json pattern → evaluate() violations 键 映射
# （gated rule 仅 refined 层启用，未启用的 rule 对应 tag 标记 covered=False，不污染召回分母）
_TAG_TO_VIOLATION = {
    "exposure_break": "exposure_break",
    "silhouette_break": "silhouette_break",
    "dead_center_composition": "dead_center",
    "warm_light_leak": "warm_light_leak",
    "style_contamination": "style_contamination",
    "face_skin_detail_fail": "skin_guard",
    "gaze_camera_fail": "eye_line",
    "absent_character_appears": "excluded_present",
    "character_swap": "swap_source_present",
    "timeline_missing": "timeline_missing",
    "audio_block_missing": "missing_audio",
    "missing_audio": "missing_audio",
    "missing_trailer": "missing_trailer",
    "timing_break": "timing_break",
    "continuity_break": "continuity_break",
    "block_coverage": "block_coverage",
}


def evaluate_negatives(
    samples: list[dict],
    tag_to_violation: dict | None = None,
    **eval_kwargs,
) -> dict:
    """负样本校验模式（video-corpus-expansion 组5）：按 failure_tags 与 evaluate() 触发违规匹配。

    每条样本：{prompt_text, failure_tags, language?, tier?, meta?, prev_final_frame?, character_list?}。
    输出每类失败模式 {recall, hits, misses, false_positives}：
    - hits：样本预期该 tag 且 evaluate 触发对应违规键
    - misses：样本预期该 tag 但未触发（漏检）
    - false_positives：样本触发了违规键但该样本预期 tags 均不映射它（误报事件，按样本×键去重）
    - covered=False：tag 无违规键映射（如 gated 未启用的规则），recall=None，不进召回分母

    常规评分路径零影响：独立入口，不改 evaluate/select_best 内部行为。
    """
    mapping = dict(tag_to_violation or _TAG_TO_VIOLATION)
    reverse: dict[str, list[str]] = {}
    for tag, vkey in mapping.items():
        reverse.setdefault(vkey, []).append(tag)
    # gated 规则动态覆盖：lock_triggers 中存在但未启用的规则，其 tag 不可判定 → covered=False
    rules = _gated_rules()
    gated_enabled = rules.get("enabled") or set()
    disabled_gated = (set((rules.get("triggers") or {}).keys()) - gated_enabled)
    uncovered_tags = {t for t, v in mapping.items() if v in disabled_gated}

    stats: dict[str, dict] = {}
    details: list[dict] = []
    total_fp = 0
    for sample in samples:
        text = str(sample.get("prompt_text") or "")
        if not text:
            continue
        sid = str(sample.get("id") or "?")
        expected = {str(t) for t in (sample.get("failure_tags") or [])}
        meta = sample.get("meta") if isinstance(sample.get("meta"), dict) else {}
        info = evaluate(
            text,
            meta,
            source_prompt=str(sample.get("source_prompt") or ""),
            language=str(sample.get("language") or "en"),
            tier=sample.get("tier"),
            prev_final_frame=sample.get("prev_final_frame"),
            character_list=sample.get("character_list"),
            **eval_kwargs,
        )
        actual = set(info["violations"].keys())
        expected_vkeys = {mapping[t] for t in expected if t in mapping}
        # 仅统计可判定（covered）的漏检；未启用 gated 规则的 tag 由 uncovered_tags 单独报告
        missed = sorted(
            t for t in expected
            if t in mapping and t not in uncovered_tags and mapping[t] not in actual
        )
        fps = sorted(v for v in actual if v not in expected_vkeys)
        total_fp += len(fps)

        for tag in expected:
            st = stats.setdefault(
                tag, {"hits": 0, "misses": 0, "false_positives": 0, "covered": tag in mapping and tag not in uncovered_tags}
            )
            if tag in mapping and tag not in uncovered_tags:
                if mapping[tag] in actual:
                    st["hits"] += 1
                else:
                    st["misses"] += 1
        # FP 事件归属到映射该违规键的 tag（该 tag 存在即累计；无归属不影响 totals）
        for vkey in fps:
            for tag in reverse.get(vkey, []):
                if tag in stats:
                    stats[tag]["false_positives"] += 1
                    break  # P1-5：样本×违规键只归属一次（多 tag 同键不重复累计；共享键的 tag 间归属为聚合性，totals 可靠）
        details.append({
            "id": sid,
            "tags": sorted(expected),
            "triggered": sorted(actual),
            "missed": missed,
            "false_positives": fps,
        })

    patterns = {}
    for tag, st in sorted(stats.items()):
        denom = st["hits"] + st["misses"]
        patterns[tag] = {
            "recall": round(st["hits"] / denom, 3) if st["covered"] and denom else None,
            "hits": st["hits"],
            "misses": st["misses"],
            "false_positives": st["false_positives"],
            "covered": st["covered"],
            "violation_key": mapping.get(tag),
        }
    covered = [p for p in patterns.values() if p["covered"]]
    uncovered = [tag for tag, p in patterns.items() if not p["covered"]]
    uncovered += sorted(t for t in uncovered_tags if t not in stats)
    return {
        "patterns": patterns,
        "totals": {
            "samples": len(samples),
            "evaluated": len(details),
            "recall": round(
                sum(p["hits"] for p in covered) / max(1, sum(p["hits"] + p["misses"] for p in covered)), 3
            ) if covered else None,
            "hits": sum(p["hits"] for p in covered),
            "misses": sum(p["misses"] for p in covered),
            "false_positives": total_fp,
            "uncovered_tags": uncovered,
        },
        "details": details,
    }
