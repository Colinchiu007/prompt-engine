# 评估器 P0-P2 深水区优化 — 技术设计

## 1. 跨语言保真（P0-1，门控）

```python
def _detect_translation_mode(source: str, prompt: str) -> bool:
    """source 含 CJK 且 prompt 不含 CJK（或反之）→ 翻译模式。"""
    src_zh = bool(re.search(r"[\u4e00-\u9fff]", str(source or "")))
    dst_zh = bool(re.search(r"[\u4e00-\u9fff]", str(prompt or "")))
    return bool(source and prompt) and src_zh != dst_zh

def _cross_lingual_fidelity(source: str, prompt: str, video: dict) -> float:
    # 0.5×要素跨语言守恒：element_keywords 中英映射，source 出现中文词 → prompt 出现对应英文词
    # 0.3×镜头结构保留：shot/camera/motion 三维（source 文本词表出现 && prompt 文本词表出现）
    # 0.2×长度比：min(src_words/prompt_words, prompt_words/src_words)
```

实现位置：`evaluate()` 保真分支（evaluator.py:598-612）前插 `if _detect_translation_mode(source_prompt, prompt): fidelity = _cross_lingual_fidelity(...)`；`checks["fidelity_method"]` 输出 `"cross_lingual"` 便于观测。

**关键兼容性**：翻译模式门控——en→en / zh→zh 路径零触碰；golden 12 条无 zh→en 样本，现有指标零变化。

## 2. 中文名字边界（P0-2）

```python
_WORD_BOUNDARY_RE = lambda token: re.compile(
    r"(?<![A-Za-z0-9])" + re.escape(token) + r"(?![A-Za-z0-9])", re.IGNORECASE)

def _contains_name(text: str, token: str, known_names: list[str]) -> bool:
    """角色名匹配：拉丁 token 走词边界；CJK token 检查是否被更长已知名字覆盖。"""
    # 1. 拉丁：_contains_word 语义
    # 2. CJK：对每个匹配位置，若 text[i:i+len] 是某更长 known_name 的前缀 → 跳过
    #    （「林晓」在「林晓雨」中 → 被覆盖 → 不命中；「林晓走进」→ 命中）
```

- 调用侧：excluded（435）、swap（449）、continuity 角色名（230/239）传 `known_names = excluded + swap 名字 + character_list` 并集（长度降序）。
- 泛词路径（`_CONTINUITY_ZH_POSTURE`、gated locks/forbidden）**不加** CJK 边界（中文无空格，正常「他站起」会假阴性）。
- `_token_occurrences`（139-148）改走 `_WORD_BOUNDARY_RE` 消除双处正则漂移。

## 3. 违规分级量化（P0-3，并行结构）

顶层 `violations: dict[str, int]` 不变（计分 `sum(violations.values())` 与 ≈40 处测试断言零破坏）；新增：

```python
checks["violations_detail"]: dict[str, {"penalty": int, "count": int, "detail": ...}]
# timing_break: {"penalty": -5, "count": beat_count, "detail": {"max_diff": 秒, "total_diff": 秒}}
# block_coverage: {"penalty": -5, "count": 1, "detail": {"hit": n, "total": m, "ratio": r}}
# 其余违规键: {"penalty": -N, "count": 1, "detail": None}
```

`select_best`/optimizer 内联排序 tie-break：`len(violations)` → `sum(abs(v) for v in violations.values())`（总惩罚量；同分决胜语义：1 个 -10 比 2 个 -5 更差）。行为变更仅在真同分时触发。

## 4. 校准门禁与工具（P0-4）

- `tests/test_golden_gate.py`（或并入 round2 测试）：加载 golden_set.json 逐条 `evaluate(length_strict=False)`，断言 `r >= 0.90` 与 `MAE <= 18`；另读 258 语料复测快照（scripts/retest_corpus.py 输出 mean/score≥90 占比）与基线（mean 90.9 / ≥90: 194）比对，断言回退不超过阈值（如 mean 跌幅 ≤2.0 且 ≥90 占比跌幅 ≤5 个百分点）。
- `scripts/eval_golden_set.py --scan-weights`：6 维权重 ±20% 步进（3^6=729 组合）输出 MAE/r 热力图 top10，只读不写。
- 全量权重搜索暂缓：golden 7/12 封顶 100（无 source fidelity 白送 20 + 三布尔镜头 + 六要素全中），5 条可导样本拟合 6 权重 = 过拟合；前置「封顶拆解」（镜头分级 + fidelity 重分配）列为 next change。

## 5. 六要素词边界（P1-1，手术式）

```python
# evaluator.py 元素命中段（572-584）改造：
for _elem, _langs in element_keywords.items():
    hits = []
    for _lang, _words in _langs.items():
        for w in _words:
            if re.search(r"[\u4e00-\u9fff\u0400-\u04FF]", w):
                if w in lower: hits.append(w)          # CJK/西里尔：子串
            else:
                if _contains_word(lower, w): hits.append(w)  # 拉丁：词边界
```

- 只影响 en 短词误击（red→category 类）；CJK/ru 零触碰。
- 风险：258 语料 elements_score 可能小幅下行（子串→词边界严格化）→ 双复测验收，若 mean 跌幅超哨兵则回退为仅对长度 ≤3 的拉丁词启用词边界。

## 6. detect_tier 阈值单一来源（P1-2）

```python
def _batch_hi(max_length: int | None) -> int:
    return min(max(400, (max_length or 1800) // 6), 833)

# detect_tier auto 分支：words > _batch_hi(max_length) → refined（原 833）
# evaluate() batch 长度上界 = _batch_hi(max_length)（同一函数）
# 豁免联动：tier 由 auto 长度兜底推断为 refined 时（checks["tier_auto"]="length"），
#   missing_trailer 不扣分（长文本无标记是形态，非引擎 refined 产物缺失）
```

- 默认 max_length=1800 → 兜底阈值 400：500-833 词无标记文本从 batch（长度 0/20）改判 refined（长度 20/20，无 trailer 扣分）→ 修正双亏区。
- `checks["tier_auto"]` 输出推断来源（marker/length/none），便于观测与测试。

## 7. 版本指纹（P1-3）

```python
_EVALUATOR_VERSION = "v0.11-deterministic"
def _asset_fingerprint() -> dict[str, str]:
    # sha256(element_keywords.json / refined_blocks.json / golden_set.json)，模块级缓存
# evaluate() 返回增补: "evaluator_version": _EVALUATOR_VERSION,
#   "assets": _asset_fingerprint()
# rest.py:181 meta["evaluator"] 改为 from video_prompt_engine.evaluator import _EVALUATOR_VERSION
```

## 8. select_best_detailed（P1-4）

`select_best(candidates, ..., detail=False)`：False 保持 3 元组；True 返回 `(prompt, meta, score, [{"prompt", "meta", "score", "checks", "violations", "advice"}])`（候选按分降序）。optimizer.py:332-343 内联排序后续可接入（本轮不改 optimizer 返回值契约）。

## 9. 剥离去重（P1-5，正确性）

evaluate() 主路径单次计算 `body_text = _strip_reference_markers(text, reference_names)`；`_check_continuity(body_text, ...)` 与 `_apply_gated_rules(body_text, ...)` 改为接收已剥离文本（函数签名加参，默认 None 时内部兜底剥离保持向后兼容）；删除内部重复 `_strip_reference_markers` 调用。修复 `[ABSENT] Roko` 在 continuity/gated 残留的正确性问题。

## 10. 空输入契约（P2-3）

`evaluate()` 开头：`if not str(prompt or "").strip(): return {"score": 0.0, "checks": {"empty": True, "violations": {}}, "tier": "batch", "violations": {}, "advice": ["空提示词"] 或 ["empty prompt"], "evaluator_version": ..., "assets": ...}`。API 层 422 保持。

## 11. 其他 P2

- **advice 排序**：`_build_advice` 先按 violations penalty 绝对值降序，再缺失要素（elements_detail score==0），最后镜头三维。
- **RU 词表**：element_keywords.json 增补 subject+полицейский/полицейских/мужчина/мужчины/женщина/женщины/группа、color+серый/серой/сером/однотонный/однотонном、environment+фон/фоне（golden ru 样本缺词，人工审校；版本号 +1）。
- **缓存线程安全**：`_GATED_RULES_CACHE` 改 `_GATED_RULES_LOADED: bool` 哨兵 + 双检锁（threading.Lock），或 `functools.lru_cache(1)`。
- **中文 2-gram 归一**：`_zh_fidelity_grams(text)` 先去高频虚字（了/着/在/的/和/与/及/或/是/有/一个/把/被/从/向/对）再取 2-gram；`fidelity` 中文路径（601-604）改用归一后 grams。

## 12. 兼容性与测试

- 增量字段：`violations_detail`/`evaluator_version`/`assets`/`checks.tier_auto`/`checks.fidelity_method`；`violations` 结构与计分不变。
- 分数分布变化面：P0-2（中文 excluded/swap 误扣消除，上行）、P1-2（400-833 无标记改判 refined+豁免，上行）、P2-2（ru elements 上行）、P2-5（zh 保真上行）、P1-1（en elements 严格化，可能下行）——**258 复测 + golden 复测双门禁验收**，哨兵：mean 跌幅 ≤2.0、score≥90 占比跌幅 ≤5pp、golden r≥0.90/MAE≤18。
- 回归锚点：`test_evaluator_p0p2.py`/`test_eval_fixes.py`/`test_corpus_expansion.py`/`test_video_evaluator_deterministic.py`/`test_higgsfield_corpus.py`/`test_image_higgsfield_alignment.py`/`test_cross_scene.py`/`test_refined_blocks.py`/`test_audio_layers.py` 全量。
