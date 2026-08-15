# 评估器 P0-P2 优化 — 技术设计

## 1. tier/form 判定（P0-1 + P2-1）

`detect_tier(prompt, video, explicit_tier)` 扩展：

```
explicit ∈ {refined, batch, asset, variant} → 原样返回
auto：
  video.shots 非空 或 正文含 NON-IP/FINAL FRAME → refined
  words > 833 → refined（长度兜底，P0-2 未落地项）
  其余 → batch
```

`evaluate()` 新增 `checks["form"]`（形态标签，仅当 auto/未显式指定时推断）：
- words < 100 → "asset"（短卡/资产卡形态）
- 100-950 词且正文含 [SHOT N]/CUT n/分镜序号 → "variant"（同 prompt 多 job 参数变体，从语料统计；简化：variant 由显式 tier 传入，auto 只推断 asset）
- 其余 → "regular"

长度带（language=en 词数 / zh 字符）：
| tier | en | zh |
|---|---|---|
| batch | 100-`min(max(400, max_length//6), 833)` | 120-2000 |
| refined | `min(500, max(150, max_length//6))`-5000 | 500-`max_length` |
| asset | 20-950 | 40-1900 |
| variant | 50-`min(max(400, max_length//6), 833)` | 80-2000 |

`length_strict=True` 时 asset/variant 同样计分（引擎候选口径只有 batch/refined，不影响现状）。

## 2. `/v1/video/evaluate` 端点（P0-2 + P2-4）

POST `/v1/video/evaluate`：

```json
{
  "prompts": ["...", "..."],          // 1-20 条，纯文本
  "compare": ["原文"],                // 可选；长度与 prompts 一致时逐条 before/after
  "tier": null,                       // 可选显式 tier（batch/refined/asset/variant）
  "language": "en",
  "max_length": null,
  "length_strict": false,             // 默认评测口径（长度不扣分只提示+梯度）
  "detail": true                      // 返回 advice/compare
}
```

响应：

```json
{
  "results": [{
    "index": 0, "score": 88.4, "tier": "batch", "form": "asset",
    "checks": { "...": "..." },
    "violations": { "missing_audio": -5 },
    "advice": ["长度 60 词低于 batch 建议带 100-833", "缺少要素：color/style"],
    "compare": null | { "score_before": 70.2, "score_delta": 18.2,
                         "by_criterion": { "elements": "+0.33", "violations": "-5" } }
  }],
  "meta": { "count": 1, "evaluator": "v0.10-deterministic" }
}
```

实现：`video_prompt_engine/api/rest.py` 新增 `@app.post("/v1/video/evaluate")`，内部调 `evaluate()`；compare 逐条调 `evaluate(compare[i])` 并算 delta。参数校验：prompts 非空 ≤20、每条非空字符串、compare 长度匹配否则 422。

## 3. 保真与运镜（P0-3 + P0-4）

**英文保真**：`source_prompt` 无中文 2-gram 时，用 `_extract_continuity_tokens(source_prompt)` 提取实体 token（复用停用词/泛词表），正文词边界命中率 = fidelity；token 为空 → fidelity=1.0（不扣分）。中文路径不变。

**运镜词表**：
```python
_TXT_SHOT = (shot, cut, establishing, close-up, closeup, wide, overhead, tracking, dolly, zoom, pan, tilt, slow-motion, 特写, 全景, 俯拍, 跟拍, 推移)
_TXT_CAMERA = (camera, lens, angle, perspective, viewpoint, 镜头, 机位, 视角, 广角, 长焦)
_TXT_MOTION = (slow-motion, pan, tilt, tracking, dolly, zoom, crane, handheld, drift, swirl, whip, 运镜, 摇镜, 推镜, 拉镜, 跟拍, 推移, 旋转, 慢动作)  # 移除 walking/running/moving
```
`has_motion` 只认镜头运动词；`has_shot` 保留 shot/cut 等（"cut" 既是镜头也是剪切，保留在 shot 维度）。

## 4. 区分度（P1-1 + P1-2）

**六要素部分命中**：每要素 `score = min(1.0, 命中不同词数 / 3)`；`elements_score = Σ/6`；`checks["elements_detail"][k] = {"hit": [...], "score": x}`。0/1 语义兼容：命中=score>0（测试断言 `elements[k] is True` 改为 score>0，或保留布尔 `elements[k]` + 新增 `elements_score_detail`——**设计决策：保留 `checks["elements"]` 布尔映射（兼容旧测试），新增 `checks["elements_detail"]`**）。

**长度梯度**（`length_strict=False`）：`words` 在带内 → 20；带外 → `20 × max(0, 1 - dist/bandwidth)`（dist=距最近边界，bandwidth=hi-lo）。`length_strict=True` 保持 0/20。

## 5. 词表资产化（P1-4 + P2-2）

新资产 `prompt_engine_core/knowledge/element_keywords.json`：

```json
{
  "version": 1,
  "elements": {
    "subject": { "en": [...], "zh": [...], "ru": ["персонаж","герой","человек","солдат","робот"] },
    "action":  { "en": [...], "zh": [...], "ru": ["бежит","движение","идёт","летит","бой"] },
    "environment": { "en": [...], "zh": [...], "ru": ["город","улица","лес","пустыня","комната"] },
    "lighting": { "en": [...], "zh": [...], "ru": ["свет","освещение","неон","блик"] },
    "color": { "en": [...], "zh": [...], "ru": ["цвет","красный","синий","золотой","чёрный"] },
    "style": { "en": [...], "zh": [...], "ru": ["стиль","кинематографичный","реалистичный","нуар"] }
  }
}
```

`prompt_engine_core/knowledge.py` 新增 `load_element_keywords()`（模块级缓存；缺失/损坏 → 回退内置默认 dict，返回 `(keywords, from_asset: bool)`）。视频 `evaluate()` 与图片 `evaluate_quality` 均改为调用它；命中逻辑统一 `any(k in lower for k in lang_words_for_all_langs)`（任一语言命中即算）。图片引擎自动获得 #52 扩充词表（行为变更为增量加分，需回归图片测试）。

**要素命中率影响**：扩充后 elements 命中更多 → 分数整体上行。258 语料复测 mean 预期上升（95.6 → ~97），区分度靠 P1-1 部分命中恢复。

## 6. 负样本 FP 修复（P1-5）

`evaluate_negatives`：`fps` 按违规键去重后，每个键归属到 `reverse[vkey]` 中**第一个**在 stats 中的 tag（样本×键只计一次）。totals.false_positives 保持样本×键口径。

## 7. 可解释性（P2-3）

`evaluate()` 新增 `advice: list[str]`（纯规则，中英文按 language 参数）。规则表（内联常量 `_ADVICE_RULES`，condition 基于 checks/violations）：
- 长度：`checks["words"]` 与带边界 → 「长度 N 词，建议带 X-Y」
- 要素缺失：`elements_detail` score==0 → 「缺少要素：X」
- 镜头：!has_shot/!has_camera/!has_motion → 「未检测到镜头/运镜描述」
- violations：逐条映射文案（excluded_present/swap/missing_trailer/missing_audio/timeline/timing/continuity/block_coverage/gated）
`enable_advice=True` 默认开（端点 detail=False 时可关）。对外返回 advice 时按 language 输出（zh→中文，en→英文，其余→en）。

## 8. golden set（P2-5）

`video_prompt_engine/knowledge/golden_set.json`：12 条（取自评估报告人工打分样本 hg-scene_74-001/012/015/020/028、hg-credits-013、hg-assets-003 等，含 human_score/rationale）。`scripts/eval_golden_set.py`：加载 → 逐条 `evaluate(length_strict=False)` → 输出 MAE/RMSE/Pearson r + 逐条对比表；退出码 0（可跑通）。golden 资产不进 few-shot（corpus_index 构建时 golden_set.json 不在 corpus/ 目录，天然隔离）。

## 9. 兼容性与测试

- `checks` 新增键：`form`/`elements_detail`/`advice`（增量）
- tier 白名单扩展（evaluate 内校验：非法值回退 auto）
- 旧测试锚点：`test_eval_fixes.py`/`test_corpus_expansion.py`/`test_video_evaluator_deterministic.py`/`test_higgsfield_corpus.py`/`test_image_higgsfield_alignment.py` 全量回归；新增 `tests/test_evaluator_p0p2.py`
- 图片引擎词表切换后：`test_image_higgsfield_alignment.py` 若断言 elements 未命中需核对（扩充是增量命中，断言"命中"不受影响；断言"未命中"仅在特定词上，需跑测确认）
