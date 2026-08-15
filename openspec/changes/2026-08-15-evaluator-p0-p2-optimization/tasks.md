# 评估器 P0-P2 优化 — 任务清单

## 1. tier/form 判定（P0-1 + P2-1）

- [ ] 1.1 `detect_tier` 增加长度兜底：auto 时 >833 词 → refined；explicit 白名单扩展 asset/variant
- [ ] 1.2 `evaluate()` 新增 `checks["form"]`（<100 词 → asset，其余 regular）；asset/variant 长度带（en/zh 表见 design §1）
- [ ] 1.3 非法 tier 值回退 auto；`length_strict=True` 时 asset/variant 同规则计分
- [ ] 1.4 测试：>833 词无标记 → refined；80 词 → batch+form=asset 且长度不判失败；tier=asset 显式 40 词合规

## 2. /v1/video/evaluate 端点（P0-2 + P2-4）

- [ ] 2.1 `rest.py` 新增 POST /v1/video/evaluate：prompts 1-20 条非空校验（422）、可选 compare/tier/language/max_length/length_strict/detail
- [ ] 2.2 响应结构：results[]（index/score/tier/form/checks/violations/advice/compare）+ meta
- [ ] 2.3 compare 逐条 evaluate 并算 score_delta + by_criterion（elements/violations/length）
- [ ] 2.4 测试：单条/批量/compare/参数校验 422/纯文本无 meta 不崩

## 3. 保真与运镜（P0-3 + P0-4）

- [ ] 3.1 英文保真：英文 source 实体 token 命中率；无实体 → 1.0 不扣分
- [ ] 3.2 `_TXT_MOTION` 移除 walking/running/moving，只保留镜头运动词
- [ ] 3.3 测试：英文 source 角色名保留高分/丢失低分；"A man walking" 不再给 has_motion

## 4. 区分度（P1-1 + P1-2）

- [ ] 4.1 六要素部分命中：elements_detail（hit 词 + score=min(1, 命中数/3)），elements 布尔映射保留
- [ ] 4.2 长度梯度：length_strict=False 按接近度 0-20；True 保持 0/20
- [ ] 4.3 测试：单要素 1 词命中 score=0.33；带外 50% 带宽 → ~10 分

## 5. 词表资产化（P1-4 + P2-2）

- [ ] 5.1 新建 `prompt_engine_core/knowledge/element_keywords.json`（6 要素 × en/zh/ru，含 #52 扩充词）
- [ ] 5.2 `core/knowledge.py` 新增 `load_element_keywords()`（缓存 + 缺失/损坏回退内置默认 + from_asset 标记）
- [ ] 5.3 视频 `evaluate()` 六要素改从 core 加载；图片 `evaluate_quality` 改从 core 加载（删 _ELEMENT_KEYWORDS）
- [ ] 5.4 测试：资产 schema（6×3 非空）、缺失回退、图片/视频加载一致、ru 词命中

## 6. 负样本 FP 修复（P1-5）

- [ ] 6.1 `evaluate_negatives` FP 按样本×违规键去重归属（多 tag 同键只计一次）
- [ ] 6.2 测试：两 tag 映射同键时单次误报只累计 1

## 7. 可解释性（P2-3）

- [ ] 7.1 `evaluate()` 新增 `advice`（长度/要素缺失/镜头/违规映射，按 language 中英文）
- [ ] 7.2 测试：短 prompt 出长度+要素建议；违规样本出违规建议

## 8. golden set（P2-5）

- [ ] 8.1 新增 `video_prompt_engine/knowledge/golden_set.json`（12 条人工评分样本）
- [ ] 8.2 新增 `scripts/eval_golden_set.py`：MAE/RMSE/Pearson r + 逐条对比表，退出码 0
- [ ] 8.3 测试：资产 schema + 脚本 dry-run

## 9. 回归与评审

- [ ] 9.1 全量测试（855+ 基线 + 新增）通过；图片引擎词表切换回归
- [ ] 9.2 双模型评审（Claude 优先，antigravity 探测）修复 Critical/Warning
- [ ] 9.3 258 语料复测快照（max/mean/score≥90 分布变化记录到报告 §8.5）
- [ ] 9.4 OpenSpec spec 更新（video-prompt-engine 评估需求扩展 + 评测端点需求）
- [ ] 9.5 提交 → PR → CI 绿 → 合并；任务归档
