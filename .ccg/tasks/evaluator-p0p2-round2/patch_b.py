import io

p = 'video_prompt_engine/evaluator.py'
s = io.open(p, encoding='utf-8', newline='').read()
orig = s

# 1) _token_occurrences 单一来源正则
old = '''    text_value = str(text or "")
    pattern = re.compile(
        r"(?<![A-Za-z0-9])" + re.escape(token) + r"(?![A-Za-z0-9])",
        flags=re.IGNORECASE,
    )
    return text_value, list(pattern.finditer(text_value))'''
new = '''    text_value = str(text or "")
    pattern = _WORD_BOUNDARY_RE(token)
    return text_value, list(pattern.finditer(text_value))'''
assert old in s
s = s.replace(old, new, 1)

# 2) _gated_rules 哨兵 + 锁
old = '''def _gated_rules() -> dict:
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
    return _GATED_RULES_CACHE'''
new = '''def _gated_rules() -> dict:
    """加载 refined_blocks.json lock_triggers/enabled_rules（哨兵+锁缓存；缺失/损坏回退空表 → 规则不启用）。"""
    global _GATED_RULES_LOADED
    if _GATED_RULES_LOADED:
        return _GATED_RULES_CACHE
    with _gated_lock():
        if _GATED_RULES_LOADED:
            return _GATED_RULES_CACHE
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
        _GATED_RULES_LOADED = True
    return _GATED_RULES_CACHE'''
assert old in s
s = s.replace(old, new, 1)

# 3) _apply_gated_rules：接收已剥离 body（P1-5 正确性）
old = '''def _apply_gated_rules(prompt: str, tier: str, violations: dict, checks: dict) -> None:
    """lock-gated 启发式（Round3 Batch C）：refined 专属；enabled_rules 控制启用；
    仅声明 lock 词时检测 forbidden（否定感知），命中 -5 advisory。"""
    if tier != "refined":
        checks["gated_hits"] = []
        return
    rules = _gated_rules()
    triggers = rules.get("triggers") or {}
    enabled = rules.get("enabled") or set()
    body = _strip_reference_markers(prompt)
    hits: list[str] = []'''
new = '''def _apply_gated_rules(body: str, tier: str, violations: dict, checks: dict) -> None:
    """lock-gated 启发式（Round3 Batch C）：refined 专属；enabled_rules 控制启用；
    仅声明 lock 词时检测 forbidden（否定感知），命中 -5 advisory。body 为已剥离引用标记的正文。"""
    if tier != "refined":
        checks["gated_hits"] = []
        return
    rules = _gated_rules()
    triggers = rules.get("triggers") or {}
    enabled = rules.get("enabled") or set()
    body = str(body or "")
    hits: list[str] = []'''
assert old in s
s = s.replace(old, new, 1)

# 4) _check_continuity：接收已剥离 body + absent 豁免
old = '''    if not prev_final_frame:
        return True, {"continuity_hits": 0, "continuity_total": 0, "continuity_ratio": None, "continuity_method": None}
    body = _strip_reference_markers(prompt)
    roster = [str(n).strip() for n in (character_list or []) if str(n or "").strip()]
    # 评审 W1：硬判据只针对"终态帧中实际出现的角色"，未入终态的副角色不要求出镜
    names = [n for n in roster if _contains_word(prev_final_frame, n)]'''
new = '''    if not prev_final_frame:
        return True, {"continuity_hits": 0, "continuity_total": 0, "continuity_ratio": None, "continuity_method": None}
    body = str(body or "")
    roster = [str(n).strip() for n in (character_list or []) if str(n or "").strip()]
    # 评审 W1：硬判据只针对"终态帧中实际出现的角色"，未入终态的副角色不要求出镜
    # P0-P2 round2：[ABSENT] 声明角色从硬判据豁免（有意缺席不判断裂）
    names = [n for n in roster if _contains_word(prev_final_frame, n) and n not in (absent_names or [])]'''
assert old in s
s = s.replace(old, new, 1)

# 4b) _check_continuity 签名
old = 'def _check_continuity(prompt: str, prev_final_frame: str, character_list: list) -> tuple[bool, dict]:'
new = 'def _check_continuity(body: str, prev_final_frame: str, character_list: list, absent_names: list[str] | None = None) -> tuple[bool, dict]:'
assert old in s
s = s.replace(old, new, 1)

# 5) _extract_absent_names 辅助（放 _check_continuity 后）
anchor = 'def _gated_rules() -> dict:'
helper = '''def _extract_absent_names(text: str, reference_names: list[str]) -> list[str]:
    """提取 [ABSENT] 标记声明的名字（P1-5 豁免语义用）。"""
    found = []
    for name in sorted(
        {str(n).strip() for n in (reference_names or []) if str(n or "").strip()},
        key=len,
        reverse=True,
    ):
        if re.search(r"\\[\\s*ABSENT\\s*\\]\\s*" + re.escape(name), str(text or ""), flags=re.IGNORECASE):
            found.append(name)
    return found


'''
assert anchor in s
s = s.replace(anchor, helper + anchor, 1)

# 6) detect_tier + _batch_hi
old = '''def detect_tier(prompt: str, video: dict | None, explicit_tier: str | None = None) -> str:
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
    return "batch"'''
new = '''def _batch_hi(max_length: int | None) -> int:
    """batch 长度上界单一来源（P1-2）：batch 上界与 refined 长度兜底阈值共用，消除 500-833 双亏区。"""
    return min(max(400, (max_length or 1800) // 6), 833)


def detect_tier(prompt: str, video: dict | None, explicit_tier: str | None = None, max_length: int | None = None) -> str:
    """tier 判定：explicit（optimizer 按 creative_level≥7 传入 refined，否则 batch）优先；无 explicit 时 auto-detect 兜底。

    自动判据：shots 非空 / prompt 含 NON-IP 或 FINAL FRAME（refined 输出特征）；
    P1-2 长度兜底：无引擎标记且 > _batch_hi(max_length) 词 → refined（阈值与 batch 上界单一来源联动）。
    语言限制（W11）：count_words 按空格切分，无空格中文不走长度兜底（中文精修通常带标记或显式 tier）。
    """
    if explicit_tier in ("refined", "batch", "asset", "variant"):
        return explicit_tier
    upper = str(prompt or "").upper()
    if (video and video.get("shots")) or "NON-IP" in upper or "FINAL FRAME" in upper:
        return "refined"
    if count_words(prompt) > _batch_hi(max_length):
        return "refined"
    return "batch"'''
assert old in s
s = s.replace(old, new, 1)

io.open(p, 'w', encoding='utf-8', newline='').write(s)
print('patched B OK, delta bytes:', len(s) - len(orig))
