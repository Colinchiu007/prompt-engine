import io

p = 'video_prompt_engine/evaluator.py'
s = io.open(p, encoding='utf-8', newline='').read()
orig = s

# 1) evaluate() 开头：空输入契约 + tier_auto + waiver
old = '''    checks = {}
    tier = detect_tier(prompt, video, explicit_tier=tier)
    checks["tier"] = tier'''
new = '''    # P2-3 空输入契约：空/纯空白 → 显式 0 分 + empty 标记（API 层已 422，引擎内部不产生白送分假分数）
    if not str(prompt or "").strip():
        return {
            "score": 0.0,
            "checks": {"empty": True, "violations": {}},
            "tier": "batch",
            "violations": {},
            "advice": ["空提示词，无法评估"] if enable_advice else [],
            "evaluator_version": _EVALUATOR_VERSION,
            "assets": _asset_fingerprint(),
        }

    checks = {}
    requested_tier = tier
    tier = detect_tier(prompt, video, explicit_tier=requested_tier, max_length=max_length)
    checks["tier"] = tier
    # P1-2：tier 推断来源（marker/length/none）+ 长度兜底进 refined 时豁免 missing_trailer
    _upper0 = str(prompt or "").upper()
    marker_based = bool(video and video.get("shots")) or "NON-IP" in _upper0 or "FINAL FRAME" in _upper0
    length_fallback = (
        tier == "refined"
        and requested_tier is None
        and not marker_based
        and count_words(prompt) > _batch_hi(max_length)
    )
    checks["tier_auto"] = "length" if length_fallback else ("marker" if marker_based and requested_tier is None else None)
    trailer_waiver = length_fallback'''
assert old in s
s = s.replace(old, new, 1)

# 2) missing_trailer 豁免
old = '''    if tier == "refined" and "NON-IP" not in upper_text:'''
new = '''    if tier == "refined" and "NON-IP" not in upper_text and not trailer_waiver:'''
assert old in s
s = s.replace(old, new, 1)

# 3) excluded/swap 走 _contains_name
old = '''    body_text = _strip_reference_markers(text, reference_names)
    if excluded:
        hit = [e for e in excluded if _contains_word(body_text, e)]
        if hit:
            violations["excluded_present"] = -10
            checks["excluded_hits"] = hit'''
new = '''    body_text = _strip_reference_markers(text, reference_names)
    known_names = reference_names  # excluded + swap 名字并集（_contains_name 长名覆盖守卫用）
    if excluded:
        hit = [e for e in excluded if _contains_name(body_text, e, known_names)]
        if hit:
            violations["excluded_present"] = -10
            checks["excluded_hits"] = hit'''
assert old in s
s = s.replace(old, new, 1)

old = '''            if _contains_word(body_text, from_name):
                hit.append(p)'''
new = '''            if _contains_name(body_text, from_name, known_names):
                hit.append(p)'''
assert old in s
s = s.replace(old, new, 1)

# 4) timing 累计（count/total）
old = '''    shots = (video or {}).get("shots") or []
    if isinstance(shots, list) and len(shots) >= 2:'''
new = '''    shots = (video or {}).get("shots") or []
    timing_count = 0
    timing_total = 0.0
    if isinstance(shots, list) and len(shots) >= 2:'''
assert old in s
s = s.replace(old, new, 1)

old = '''                if diff > 0:
                    violations["timing_break"] = -5'''
new = '''                if diff > 0:
                    timing_count += 1
                    timing_total += diff
                    violations["timing_break"] = -5'''
assert old in s
s = s.replace(old, new, 1)

# 5) continuity 调用：已剥离 body + absent 豁免
old = '''    if prev_final_frame:
        continuity_ok, continuity_checks = _check_continuity(prompt, prev_final_frame, character_list or [])'''
new = '''    if prev_final_frame:
        absent_names = _extract_absent_names(text, reference_names)
        continuity_ok, continuity_checks = _check_continuity(body_text, prev_final_frame, character_list or [], absent_names)'''
assert old in s
s = s.replace(old, new, 1)

# 6) block_coverage 提升 hits/ratio 到外层（violations_detail 用）
old = '''    blocks = clean_blocks((video or {}).get("blocks"))
    if tier == "refined" and blocks:
        non_empty = list(blocks)
        if non_empty:
            rendered_names = rendered_block_names(prompt)
            hits = sum(1 for k in non_empty if k in rendered_names)
            ratio = hits / len(non_empty)'''
new = '''    blocks = clean_blocks((video or {}).get("blocks"))
    block_hits = 0
    block_ratio = 0.0
    if tier == "refined" and blocks:
        non_empty = list(blocks)
        if non_empty:
            rendered_names = rendered_block_names(prompt)
            hits = sum(1 for k in non_empty if k in rendered_names)
            ratio = hits / len(non_empty)
            block_hits, block_ratio = hits, ratio'''
assert old in s
s = s.replace(old, new, 1)

old = '''            checks["block_coverage"] = {"hit": hits, "total": len(non_empty), "ratio": round(ratio, 3)}'''
new = '''            checks["block_coverage"] = {"hit": block_hits, "total": len(non_empty), "ratio": round(block_ratio, 3)}'''
assert old in s
s = s.replace(old, new, 1)

old = '''            min_ratio = float((_gated_rules().get("coverage") or {}).get("min_ratio", 0.8))
            if ratio < min_ratio:
                violations["block_coverage"] = -5'''
new = '''            min_ratio = float((_gated_rules().get("coverage") or {}).get("min_ratio", 0.8))
            if block_ratio < min_ratio:
                violations["block_coverage"] = -5'''
assert old in s
s = s.replace(old, new, 1)

# 7) _apply_gated_rules 调用：已剥离 body
old = '''    _apply_gated_rules(prompt, tier, violations, checks)
    checks["violations"] = violations'''
new = '''    _apply_gated_rules(body_text, tier, violations, checks)
    checks["violations"] = violations
    # P0-3 违规分级量化：violations_detail 并行结构（顶层 violations 保持 dict[str,int] 计分兼容）
    violations_detail: dict = {}
    for _key, _val in violations.items():
        violations_detail[_key] = {"penalty": _val, "count": 1, "detail": None}
    if "timing_break" in violations:
        violations_detail["timing_break"] = {
            "penalty": -5,
            "count": timing_count,
            "detail": {
                "max_diff": round(timing_diff, 2) if timing_diff is not None else None,
                "total_diff": round(timing_total, 2),
            },
        }
    if "block_coverage" in violations:
        violations_detail["block_coverage"] = {
            "penalty": -5,
            "count": 1,
            "detail": {"hit": block_hits, "total": len(non_empty) if tier == "refined" and blocks else 0, "ratio": round(block_ratio, 3)},
        }
    checks["violations_detail"] = violations_detail'''
assert old in s
s = s.replace(old, new, 1)

# 8) 六要素词边界（手术式：拉丁词边界+复数容错，CJK/西里尔子串）
old = '''    element_keywords, _kw_from_asset = load_element_keywords()
    for _elem, _langs in element_keywords.items():
        _toks = list(dict.fromkeys(w for _v in _langs.values() for w in _v))
        _hits = sorted({t for t in _toks if t in lower})
        elements_detail[_elem] = {
            "hit": bool(_hits), "words": _hits[:8], "score": round(min(1.0, len(_hits) / 3.0), 3),
        }'''
new = '''    element_keywords, _kw_from_asset = load_element_keywords()
    for _elem, _langs in element_keywords.items():
        _hits: list[str] = []
        for _lang, _words in _langs.items():
            for _w in _words:
                _w = str(_w or "").strip()
                if not _w or _w in _hits:
                    continue
                if re.search(r"[\\u4e00-\\u9fff\\u0400-\\u04ff]", _w):
                    if _w in lower:
                        _hits.append(_w)
                elif (
                    _contains_word(lower, _w)
                    or _contains_word(lower, _w + "s")
                    or _contains_word(lower, _w + "es")
                ):
                    _hits.append(_w)
        elements_detail[_elem] = {
            "hit": bool(_hits), "words": _hits[:8], "score": round(min(1.0, len(_hits) / 3.0), 3),
        }'''
assert old in s
s = s.replace(old, new, 1)

# 9) 保真三路径：跨语言（门控）/中文归一/英文词干 + fidelity_method
old = '''    # 4) 保真（source 实体命中：中文 2-gram；英文实体 token 词边界命中——P0-3 英文保真补盲区）
    fidelity = 1.0
    if source_prompt:
        zh_chars = re.findall(r"[\\u4e00-\\u9fff]{2,}", source_prompt)
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
    checks["fidelity"] = fidelity'''
new = '''    # 4) 保真三路径（P0-1/P2-5）：跨语言翻译模式（门控）/ 中文 2-gram 归一 / 英文实体词干命中
    fidelity = 1.0
    checks["fidelity_method"] = "none"
    if source_prompt:
        if _detect_translation_mode(source_prompt, prompt):
            fidelity = _cross_lingual_fidelity(source_prompt, prompt)
            checks["fidelity_method"] = "cross_lingual"
        else:
            zh_chars = re.findall(r"[\\u4e00-\\u9fff]{2,}", source_prompt)
            if zh_chars:
                src_grams = _zh_fidelity_grams(source_prompt)
                if src_grams:
                    hit = len(src_grams & _zh_fidelity_grams(prompt))
                    fidelity = round(hit / len(src_grams), 3)
                checks["fidelity_method"] = "zh2gram"
            else:
                tokens = _extract_continuity_tokens(source_prompt)
                if tokens:
                    # W3：词形归一（robot→robots/run→runs）——全词边界对复数/时态假阴性，保真路径轻量容忍
                    prompt_stems = _en_stems(prompt)
                    hits = [t for t in tokens if _contains_word(prompt, t) or _stem_en(t) in prompt_stems]
                    fidelity = round(len(hits) / len(tokens), 3)
                checks["fidelity_method"] = "wordlist"
    checks["fidelity"] = fidelity'''
assert old in s
s = s.replace(old, new, 1)

# 10) 返回版本指纹
old = '''    return {
        "score": round(max(0, min(100, score)), 1),
        "checks": checks,
        "tier": tier,
        "violations": violations,
        "advice": _build_advice(prompt, checks, violations, language) if enable_advice else [],
    }'''
new = '''    return {
        "score": round(max(0, min(100, score)), 1),
        "checks": checks,
        "tier": tier,
        "violations": violations,
        "advice": _build_advice(prompt, checks, violations, language) if enable_advice else [],
        "evaluator_version": _EVALUATOR_VERSION,
        "assets": _asset_fingerprint(),
    }'''
assert old in s
s = s.replace(old, new, 1)

io.open(p, 'w', encoding='utf-8', newline='').write(s)
print('patched C OK, delta bytes:', len(s) - len(orig))
