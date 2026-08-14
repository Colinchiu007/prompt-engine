## Why

视频引擎（8020, `video_prompt_engine/`）已落地 Higgsfield 三件套：多候选择优（`select_best`）、违规扣分（violations：缺席角色/swap/尾行/音频）、tier 层级长度（batch 100-400 词 / refined 500-5,000 词）。图片引擎（`prompt_engine/`）同样有 `num_candidates` 多候选能力，但候选生成后直接取 `candidates[0]`，没有择优、没有违规扣分、长度判据无层级——创意等级≥7 的"精修级"图片提示词与批量级共用同一套评估口径，引擎无法选出质量最优候选，也无法阻止缺席角色/角色替换类违规进入结果。

## What Changes

- `prompt_engine/evaluator.py` 新增**确定性启发式评分**（无 LLM 调用，供多候选择优）：六要素命中 + 长度层级 + 源保真 + 违规扣分，返回 `{score, checks, tier, violations}`；新增 `detect_tier()` 与 `select_best()`。
- `prompt_engine/models.py`：`OptimizeRequest` 新增双向约束字段 `excluded_characters: list[str]`、`no_swap_pairs: list[list[str]]`（语义对齐视频引擎契约；非法形态校验在 rest/服务层）。
- `prompt_engine/optimizer.py`：`num_candidates>1` 时用启发式评分对候选排序，最高分作为 `optimized_prompt`，`candidates` 按分数降序返回；tier 判定复用视频规则（`creative_level>=7` → refined，否则 batch）。
- 违规扣分（**图片适用子集**）：`excluded_present -10`、`swap_source_present -10`；`missing_trailer` / `missing_audio` 对图片引擎为 N/A，不适用不扣分。
- tier 层级长度（**图片适配波段**，见 design）：batch 与 refined 分开判据，上界与 `max_length` 联动并封顶，避免大预算下静默扩张。
- 既有 LLM 对比评估（compare API 的 5 维 before/after）**保持不变**；视频领域经 `prompt_engine` 的 legacy 路径行为不变。

## Capabilities

### New Capabilities
- `image-prompt-quality`: 图片提示词质量评估与多候选择优——启发式评分、违规扣分（excluded/swap）、tier 层级长度、select_best 行为契约。

### Modified Capabilities
（无——现有唯一 spec `video-prompt-engine` 不涉及图片引擎行为变更）

## Impact

- 代码：`prompt_engine/evaluator.py`、`prompt_engine/optimizer.py`、`prompt_engine/models.py`、`prompt_engine/api/rest.py`（新字段透传与校验）、`prompt_engine/strategies/base.py`（如注入 tier 提示，最小化）。
- 测试：新增 `tests/test_image_higgsfield_alignment.py`（tier 判定/长度波段/违规扣分/select_best 排序/optimizer 集成/回归）；既有 654 测试不得回归。
- 依赖：无新第三方依赖（启发式评分纯标准库，复用 `prompt_engine_core.text`）。
- 外部契约：`/v1/optimize` 请求体新增可选字段（向后兼容，缺省不启用扣分）。
