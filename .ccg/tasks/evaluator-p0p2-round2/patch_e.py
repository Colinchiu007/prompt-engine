import io

p = 'video_prompt_engine/api/rest.py'
s = io.open(p, encoding='utf-8', newline='').read()
orig = s
nl = '\r\n'
old = 'from video_prompt_engine.evaluator import evaluate as evaluate_prompt' + nl
new = 'from video_prompt_engine.evaluator import evaluate as evaluate_prompt, _EVALUATOR_VERSION' + nl
assert old in s, 'import anchor missing'
s = s.replace(old, new, 1)
old2 = '    return {"results": results, "meta": {"count": len(results), "evaluator": "v0.10-deterministic"}}'
new2 = '    return {"results": results, "meta": {"count": len(results), "evaluator": _EVALUATOR_VERSION}}'
assert old2 in s, 'meta anchor missing'
s = s.replace(old2, new2, 1)
io.open(p, 'w', encoding='utf-8', newline='').write(s)
print('rest.py OK, delta:', len(s) - len(orig))

p2 = 'video_prompt_engine/optimizer.py'
s2 = io.open(p2, encoding='utf-8', newline='').read()
orig2 = s2
old3 = 'scored.append((_info["score"], len(_info.get("violations") or {}), _idx, _p, _m))'
new3 = 'scored.append((_info["score"], sum(abs(v) for v in (_info.get("violations") or {}).values()), _idx, _p, _m))'
assert old3 in s2, 'optimizer anchor missing'
s2 = s2.replace(old3, new3, 1)
io.open(p2, 'w', encoding='utf-8', newline='').write(s2)
print('optimizer.py OK, delta:', len(s2) - len(orig2))
