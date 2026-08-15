# 评估器 P0-P2 优化（detect_tier 兜底 / evaluate 端点 / 保真与运镜 / 区分度 / 词表资产化 / 形态与多语种）

## Why

2026-08-15 质量评估（`docs/VIDEO-PROMPT-ENGINE-QUALITY-EVAL-2026-08-15.md`）修复了 P0-1/P1-1/P1-2/P1-3/P1-4，但 **P0-2（auto-tier 长度兜底）未落地**：`detect_tier` 仍只认 `shots/NON-IP/FINAL FRAME`，真实用户输入 70/258 误分层、140 条被误判 batch 后触发长度扣 20 分。同时暴露的遗留缺口：

- **运营后台接入缺口**：视频侧无 `/v1/video/evaluate` 端点（图片侧有 `/v1/evaluate`），后台「提示词评测」接不到视频引擎。
- **英文保真盲区**：`fidelity` 只对中文 source 做 2-gram 命中，英文 source 完全不算保真分。
- **运镜误判**：`_TXT_MOTION` 把 `walking/running/moving` 等主体运动词当镜头运动，纯动作描述白拿 15 分。
- **分数饱和**：258 语料复测 score≥90 占 231/258，评测口径区分度不足；六要素 0/1 二值、`length_strict=False` 长度 0/20 二值。
- **词表漂移**：视频六要素词表内联于 `evaluate()`，图片引擎 `_ELEMENT_KEYWORDS` 为旧版子集（缺 #52 扩充），双份维护必漂移。
- **负样本 FP 计数缺陷**：`evaluate_negatives` 中一个违规键映射多 tag 时，一次误报重复累计到每个 tag。
- **形态/语种缺口**：语料 `tier:asset/variant` 52 条无对应层；六要素词表仅 en/zh，俄语 6/6 全 miss。

## What Changes

### P0（接入前必做）
- **P0-1 `detect_tier` 长度兜底**：无引擎标记时按词数推断（>833 词 → refined；其余 batch）；`<100` 词识别为 asset 形态（`checks["form"]`），不判 batch 长度失败。
- **P0-2 新增 `/v1/video/evaluate`**：纯文本评测端点（单条/批量 ≤20、可选 before/after 对比、`length_strict` 默认 False 评测口径、可解释建议输出）。
- **P0-3 英文保真**：英文 source 按实体 token 词边界命中率计保真分（复用承接 token 提取；无实体不扣分）。
- **P0-4 运镜词表拆分**：`_TXT_MOTION` 移除主体运动词（walking/running/moving），只保留镜头运动词（pan/tilt/dolly/tracking/zoom/推移/旋转等）。

### P1（区分度与选择质量）
- **P1-1 六要素部分命中**：每要素按命中词数计 0-1 分（命中 ≥3 词满分），`elements_score` 保留 0-1 语义；输出命中明细。
- **P1-2 长度梯度分**：`length_strict=False` 时长度按接近合法带的比例给 0-20 梯度分，替代 0/20 二值。
- **P1-3 `select_best` tie-break**：同分时违规数少者胜，保持稳定（先出现者优先）。
- **P1-4 六要素词表资产化**：新建 `prompt_engine_core/knowledge/element_keywords.json`（6 要素 × en/zh/ru），视频 `evaluate()` 与图片 `evaluate_quality` 统一从 core 加载（缺失/损坏回退内置默认，零回归）。
- **P1-5 负样本 FP 计数修复**：误报按「样本×违规键」去重归属，多 tag 映射同一键不再重复累计。

### P2（能力扩展）
- **P2-1 asset/variant 形态建模**：`tier` 白名单扩展 asset/variant（asset 20-950 词、variant 50-833 词）；`checks["form"]` 输出形态标签。
- **P2-2 多语种六要素**：词表资产增加 ru 词表，任一语言命中即算要素命中。
- **P2-3 可解释性输出**：`evaluate()` 增加 `advice` 字段（纯规则生成：长度/要素/镜头/违规对应建议文案），供运营后台展示。
- **P2-4 before/after 对比语义**：`/v1/video/evaluate` 支持 `compare` 字段，输出逐维 delta（score/elements/violations）。
- **P2-5 golden set 校准资产**：新增 `knowledge/golden_set.json`（人工评分样本）+ `scripts/eval_golden_set.py`（MAE/RMSE/相关系数）。

## Capabilities

### New Capabilities
- 无（归入既有 `video-prompt-engine` 规格）

### Modified Capabilities
- `video-prompt-engine`：扩展「评估与择优机制」需求（tier 兜底/形态/保真/运镜/部分命中/梯度/tie-break/advice/compare），新增「评测端点」需求（`/v1/video/evaluate`），扩展「知识库资产」（element_keywords/golden_set）。
- `image-prompt-quality`：六要素词表改用共享资产（消除漂移，自动获得扩充词表）。

## Impact

- 文件：`video_prompt_engine/evaluator.py`、`video_prompt_engine/api/rest.py`、`prompt_engine/evaluator.py`（词表加载）、`prompt_engine_core/knowledge.py`（加载函数）、新增 `prompt_engine_core/knowledge/element_keywords.json`、`video_prompt_engine/knowledge/golden_set.json`、`scripts/eval_golden_set.py`、`openspec/specs/video-prompt-engine/spec.md`
- 测试：新增 `tests/test_evaluator_p0p2.py`（预估 25-35 项）+ 图片/负样本回归全量
- 兼容性：`evaluate()` 返回结构新增字段（advice/form）为增量；tier 白名单扩展为增量；词表加载缺失回退零回归
