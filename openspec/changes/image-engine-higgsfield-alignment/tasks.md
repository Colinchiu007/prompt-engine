## 1. 测试先行（TDD）

- [x] 1.1 新增 `tests/test_image_higgsfield_alignment.py`：tier 判定（explicit/auto 兜底 batch）
- [x] 1.2 测试层级长度波段：batch/refined 各自 en 词数与 zh 字符数边界、上界联动 max_length、refined 小预算下界自适应、上界封顶
- [x] 1.3 测试违规扣分：excluded 命中 -10 / swap 源命中 -10 / 字段为空 N/A / `[ABSENT]` `<<<>>>` 标记剥离不自罚 / 词边界防误击（中文"关"vs"关键"）
- [x] 1.4 测试 select_best 与评分确定性：同输入同输出、0-100 范围、降序排序、多候选择优（72/88/65 → 88 最优）
- [x] 1.5 测试 optimizer 集成：num_candidates=3 图片域 → optimized_prompt 为最高分候选、candidates 降序；num_candidates=1 → 输出与既有路径一致（回归）
- [x] 1.6 测试字段收敛（rest 边界）：合法数组生效 / 字符串形态兼容 / 非法形态丢弃不抛错 / 超限截断（excluded≤20、no_swap≤10）
- [x] 1.7 回归测试：compare 模式（LLM 5 维）不变；`domain=video` legacy 路径输出不变；既有 654 基线全过

## 2. 模型与收敛

- [x] 2.1 `prompt_engine/models.py`：`OptimizeRequest` 新增 `excluded_characters: list[str]`、`no_swap_pairs: list[list[str]]`（默认空、可选）
- [x] 2.2 `prompt_engine/api/rest.py`：请求规范化——excluded 兼容字符串/数组、no_swap 二元组校验、非法丢弃 + warning、超限截断

## 3. 评估器实现

- [x] 3.1 `prompt_engine/evaluator.py`：新增 `_contains_word`（词边界/整名）、`_strip_reference_markers`（`[ABSENT]`/`<<<>>>`）、`detect_tier`、`count_words`（复用 video 语义）
- [x] 3.2 新增 `evaluate(prompt, meta, source_prompt, language, tier, max_length)`：六要素 + 层级长度 + 保真 + violations（excluded -10 / swap -10），返回 `{score, checks, tier, violations}`；语言 auto（源含中文 → zh）
- [x] 3.3 新增 `select_best(candidates, ...)`：评分降序取最优

## 4. Optimizer 接入

- [x] 4.1 `prompt_engine/optimizer.py`：tier 判定（creative_level>=7 → refined）；图片域 `num>1` 时按 `evaluate` 评分降序，最优为 `optimized_prompt`、`candidates` 降序；`is_video` 分支不接入
- [x] 4.2 缓存/错误路径核查：择优不破坏缓存 key 语义；异常回退路径保持原样

## 5. 验证与评审

- [ ] 5.1 全量 pytest 通过（含既有 654 基线）
- [ ] 5.2 双模型评审（antigravity 不可用则 Claude 降级并记录）0 Critical
- [ ] 5.3 CHANGELOG/README 补档 + openspec sync-specs（spec 归档到 main spec）+ CCG task 归档
