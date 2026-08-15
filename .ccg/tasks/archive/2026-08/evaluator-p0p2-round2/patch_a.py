import io

p = 'video_prompt_engine/evaluator.py'
s = io.open(p, encoding='utf-8', newline='').read()
orig = s

# 1) 头部：import 后插入版本常量与指纹
anchor = 'from prompt_engine_core.knowledge import load_element_keywords\n'
block1 = anchor + '''
# P0-P2 round2：评估器版本指纹（rest.py meta 复用，消除双处硬编码漂移）
_EVALUATOR_VERSION = "v0.11-deterministic"
_ASSET_FP_CACHE: dict | None = None


def _asset_fingerprint() -> dict[str, str]:
    """评估相关资产 sha256（element_keywords/refined_blocks/golden_set），模块级缓存。"""
    global _ASSET_FP_CACHE
    if _ASSET_FP_CACHE is not None:
        return _ASSET_FP_CACHE
    import hashlib
    from pathlib import Path
    engine_base = Path(__file__).resolve().parent / "knowledge"
    core_base = Path(__file__).resolve().parent.parent / "prompt_engine_core" / "knowledge"
    _ASSET_FP_CACHE = {}
    for name in ("element_keywords", "refined_blocks", "golden_set"):
        candidate = (core_base / f"{name}.json") if name == "element_keywords" else (engine_base / f"{name}.json")
        try:
            _ASSET_FP_CACHE[name] = hashlib.sha256(candidate.read_bytes()).hexdigest()
        except OSError:
            _ASSET_FP_CACHE[name] = "missing"
    return _ASSET_FP_CACHE


def _WORD_BOUNDARY_RE(token: str) -> re.Pattern:
    """拉丁词边界正则单一来源（合并 _contains_word 与 _token_occurrences 双处实现）。"""
    return re.compile(
        r"(?<![A-Za-z0-9])" + re.escape(token) + r"(?![A-Za-z0-9])",
        flags=re.IGNORECASE,
    )
'''
assert anchor in s
s = s.replace(anchor, block1, 1)

# 2) gated 缓存哨兵 + 锁
anchor2 = '_GATED_RULES_CACHE: dict = {}\n'
block2 = anchor2 + '''_GATED_RULES_LOADED = False
_GATED_RULES_LOCK = None


def _gated_lock() -> object:
    global _GATED_RULES_LOCK
    if _GATED_RULES_LOCK is None:
        import threading
        _GATED_RULES_LOCK = threading.Lock()
    return _GATED_RULES_LOCK
'''
assert anchor2 in s
s = s.replace(anchor2, block2, 1)

# 3) _contains_word 改造为单一来源正则
old_cw = '''    token = str(token or "").strip()
    if not token or len(token) < 2:
        return False
    return (
        re.search(
            r"(?<![A-Za-z0-9])" + re.escape(token) + r"(?![A-Za-z0-9])",
            str(text or ""),
            flags=re.IGNORECASE,
        )
        is not None
    )'''
new_cw = '''    token = str(token or "").strip()
    if not token or len(token) < 2:
        return False
    return _WORD_BOUNDARY_RE(token).search(str(text or "")) is not None'''
assert old_cw in s
s = s.replace(old_cw, new_cw, 1)

# 4) _strip_reference_markers 前插入名字边界/翻译模式/中文归一工具
anchor3 = 'def _strip_reference_markers('
tools = '''def _contains_name(text: str, token: str, known_names: list[str]) -> bool:
    """角色名匹配（P0-2）：拉丁 token 词边界；CJK token 检查是否被更长已知名字覆盖。

    中文无空格，名字后紧跟汉字是常态（「林晓走进」），不能加 CJK 边界；
    但 excluded 角色「林晓」不得命中「林晓雨」——当命中位置是某更长已知名字的
    前缀时跳过（known_names = excluded + swap + character_list 并集）。
    泛词路径（posture/gated locks）不经过此函数，维持子串语义。
    """
    token = str(token or "").strip()
    text_value = str(text or "")
    if not token or len(token) < 2:
        return False
    if not re.search(r"[\\u4e00-\\u9fff]", token):
        return _contains_word(text_value, token)
    longer = sorted(
        (str(n).strip() for n in (known_names or []) if len(str(n or "").strip()) > len(token) and token in str(n)),
        key=len,
        reverse=True,
    )
    for match in re.finditer(re.escape(token), text_value):
        start = match.start()
        covered = any(
            text_value[start:start + len(name)] == name
            or (start - 1 >= 0 and text_value[start - 1:start - 1 + len(name)] == name)
            for name in longer
        )
        if not covered:
            return True
    return False


def _detect_translation_mode(source: str, prompt: str) -> bool:
    """翻译模式（P0-1）：source 含 CJK 且 prompt 不含（或反之），且双方非空。"""
    src, dst = str(source or ""), str(prompt or "")
    if not src or not dst:
        return False
    src_zh = bool(re.search(r"[\\u4e00-\\u9fff]", src))
    dst_zh = bool(re.search(r"[\\u4e00-\\u9fff]", dst))
    return src_zh != dst_zh


def _cross_lingual_fidelity(source: str, prompt: str) -> float:
    """翻译模式保真：0.5 要素跨语言守恒 + 0.3 镜头结构保留 + 0.2 长度比。

    仅 _detect_translation_mode 为真时启用（门控新路径，en→en/zh→zh 零触碰）。
    局限（声明）：要素为 6 维粗粒度类别，测的是「类别保留」而非逐实体语义保真。
    """
    element_keywords, _ = load_element_keywords()
    src_zh = str(source or "")
    dst_en = str(prompt or "").lower()

    conserved = 0.0
    for _elem, _langs in element_keywords.items():
        zh_hit = any(str(w) in src_zh for w in _langs.get("zh", []))
        en_hit = any(
            _contains_word(dst_en, str(w))
            or _contains_word(dst_en, str(w) + "s")
            or _contains_word(dst_en, str(w) + "es")
            for w in _langs.get("en", [])
        )
        if zh_hit and en_hit:
            conserved += 1.0
    conserved /= max(1, len(element_keywords))

    dims = (
        (("镜头", "景别", "特写", "全景", "俯拍", "跟拍", "推移"),
         ("shot", "cut", "close-up", "closeup", "wide", "overhead", "tracking", "dolly")),
        (("机位", "视角", "广角", "长焦"),
         ("camera", "angle", "perspective", "viewpoint")),
        (("运镜", "摇镜", "推镜", "拉镜", "旋转", "慢动作"),
         ("slow-motion", "pan", "tilt", "tracking", "dolly", "zoom", "crane", "handheld")),
    )
    kept = 0.0
    for zh_toks, en_toks in dims:
        src_has = any(t in src_zh for t in zh_toks)
        dst_has = any(_contains_word(dst_en, t) for t in en_toks)
        if src_has and dst_has:
            kept += 1.0
    kept /= len(dims)

    src_words = max(1, len(str(source).split()))
    dst_words = max(1, len(str(prompt).split()))
    ratio = min(src_words / dst_words, dst_words / src_words)
    return round(0.5 * conserved + 0.3 * kept + 0.2 * ratio, 3)


_ZH_STOP_CHARS = frozenset("了着在的与及或是有一把被从向对到里个这那之也又都")


def _zh_fidelity_grams(text: str) -> set[str]:
    """中文保真 2-gram（P2-5）：去高频虚字/标点/空白后滑动取二元组集合，容忍语序与虚字差异。"""
    cleaned = "".join(
        ch for ch in str(text or "")
        if ch not in _ZH_STOP_CHARS and not ch.isspace() and ch not in "，。！？；、,.!?;：:"
    )
    if len(cleaned) < 2:
        return set()
    return {cleaned[i:i + 2] for i in range(len(cleaned) - 1)}


'''
assert anchor3 in s
s = s.replace(anchor3, tools + anchor3, 1)

io.open(p, 'w', encoding='utf-8', newline='').write(s)
print('patched A OK, delta bytes:', len(s) - len(orig))
