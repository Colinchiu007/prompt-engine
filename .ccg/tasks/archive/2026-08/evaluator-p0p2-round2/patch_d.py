import io

p = 'video_prompt_engine/evaluator.py'
s = io.open(p, encoding='utf-8', newline='').read()
orig = s

# 1) _build_advice：违规按 penalty 绝对值降序（P2-1）
old = '''    for key in (violations or {}):
        text = _ADVICE_VIOLATION_TEXT.get(key)
        if text:
            advice.append(text[0] if zh else text[1])
        else:
            advice.append(f"违反规则：{key}" if zh else f"rule violation: {key}")
    return advice'''
new = '''    for key, _val in sorted((violations or {}).items(), key=lambda kv: abs(kv[1]), reverse=True):
        text = _ADVICE_VIOLATION_TEXT.get(key)
        if text:
            advice.append(text[0] if zh else text[1])
        else:
            advice.append(f"违反规则：{key}" if zh else f"rule violation: {key}")
    return advice'''
assert old in s
s = s.replace(old, new, 1)

# 2) select_best：tie-break 升级 sum(abs(penalty)) + detail=True（P0-3/P1-4）
old = '''def select_best(
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
    return best[0], best[1], best[2]'''
new = '''def select_best(
    candidates: list[tuple[str, dict]],
    source_prompt: str = "",
    language: str = "en",
    tier: str | None = None,
    max_length: int | None = None,
    prev_final_frame: str | None = None,
    character_list: list | None = None,
    length_strict: bool = True,
    detail: bool = False,
) -> tuple[str, dict, float] | tuple[str, dict, float, list[dict]]:
    """多候选择优：返回 (prompt, video_meta, score)，分数最高者优先；
    同分时违规总惩罚量小者胜（P0-3：sum(abs(penalty))，1 个 -10 比 2 个 -5 更差），
    仍同分取先出现者（稳定排序）。
    detail=True 返回 4 元组 (prompt, meta, score, candidates_info)——每候选
    checks/violations/advice/violations_penalty 明细（按分降序），供运营解释「为什么选它」。"""
    scored: list[tuple[float, int, str, dict, dict]] = []
    for prompt, meta in candidates:
        info = evaluate(
            prompt, meta, source_prompt=source_prompt, language=language, tier=tier,
            max_length=max_length, prev_final_frame=prev_final_frame, character_list=character_list,
            length_strict=length_strict,
        )
        score = float(info["score"])
        penalty = sum(abs(v) for v in (info.get("violations") or {}).values())
        scored.append((score, penalty, prompt, meta, info))
    scored.sort(key=lambda x: (-x[0], x[1]))  # 稳定排序：同分同惩罚保留先出现者
    if not scored:
        return ("", {}, 0.0, []) if detail else ("", {}, 0.0)
    if detail:
        infos = [
            {
                "prompt": p, "meta": m, "score": sc,
                "checks": i.get("checks"), "violations": i.get("violations"),
                "advice": i.get("advice"), "violations_penalty": pen,
            }
            for sc, pen, p, m, i in scored
        ]
        return scored[0][2], scored[0][3], scored[0][0], infos
    return scored[0][2], scored[0][3], scored[0][0]'''
assert old in s
s = s.replace(old, new, 1)

io.open(p, 'w', encoding='utf-8', newline='').write(s)
print('patched D OK, delta bytes:', len(s) - len(orig))
