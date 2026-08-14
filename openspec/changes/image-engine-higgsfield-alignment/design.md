## Context

图片引擎（`prompt_engine/`）当前状态：`OptimizeRequest.num_candidates` 支持 1-5，但 `optimize()` 候选循环后直接取 `candidates[0]` 作为主输出；`evaluator.py` 仅提供 LLM 对比评估（compare 模式），无确定性评分、无违规扣分、无层级长度判据；`OptimizeRequest` 无 `excluded_characters`/`no_swap_pairs` 字段；`max_length` 范围 50-2000（默认 500）。

参照实现：视频引擎 `video_prompt_engine/evaluator.py`（`detect_tier`/`evaluate`/`select_best`，violations：excluded -10 / swap -10 / 缺尾行 -10 / 缺 Audio -5，batch 100-400 词 / refined 500-5000 词，`[ABSENT]`/`<<<>>>` 标记剥离）与 `optimizer.py`（`creative_level>=7 → refined`，候选评分降序）。两引擎共享 `prompt_engine_core`（text/registry/vector_store 等），但评估逻辑目前仅在视频侧。

## Goals / Non-Goals

**Goals:**
- 图片引擎获得与视频引擎一致的择优机制：多候选确定性评分排序、violations 扣分（图片适用子集）、tier 层级长度判据。
- 新字段（excluded_characters/no_swap_pairs）从 API 边界透传到评分，非法形态丢弃不抛错。
- 单候选路径、compare 模式、视频 legacy 路径零行为变化。

**Non-Goals:**
- 不把视频引擎的 `missing_trailer`/`missing_audio` 扣分引入图片（领域无此概念）。
- 不重构视频引擎评估逻辑（不在本次收敛共享，避免扩大影响面；语义对齐 + 未来可收敛）。
- 不在图片 system prompt 中注入 tier 形态提示（精修形态已由 `creative_level` 控制，tier 仅作评估口径）。
- 不引入新第三方依赖。

## Decisions

### D1: 评分函数签名与视频对齐（meta dict 形态）
图片侧 `evaluate(prompt, meta, source_prompt, language, tier, max_length)` 复用视频签名；图片调用时传入轻量 meta：`{"excluded_characters": [...], "no_swap_pairs": [...]}`（源自 request 字段）。理由：机制完全一致，测试可迁移，未来收敛到共享内核时零签名破坏。替代方案（图片专用参数列表）被否——双签名增加长期维护成本。

### D2: 层级长度波段按图片领域适配
- batch（en 词数）：`30 ≤ words ≤ min(max(300, max_length//6), 500)`；zh 字符：`60 ≤ chars ≤ min(max(1000, max_length), 2000)`
- refined（en 词数）：`min(500, max(100, max_length//6)) ≤ words ≤ min(max(500, max_length//4), 2000)`；zh 字符：`300 ≤ chars ≤ max_length`
- 默认 `max_length=500` 时：batch en 30-300 词、refined en 100-500 词（500 字符≈100 词，区间实际上限由词数决定）。
- 视频 refined 上界 5000 词对图片不适用（图片 `max_length` 上限 2000 字符≈400 词），图片上界封顶 2000 词（实际由 `max_length//4` 主导）。
- 六要素词典沿用视频同款（主体/动作/环境/光影/色彩/风格），图片静态构图同样适用。

### D3: violations 图片子集 + 标记剥离复用
扣分项仅 `excluded_present -10`、`swap_source_present -10`；`_contains_word`（词边界/整名匹配，中文防"关"误击"关键"）与 `_strip_reference_markers`（`[ABSENT]`/`<<<>>>` 剥离）从视频实现复制到图片 `evaluator.py`，注释标注与视频语义一致（含评审 C1：仅剥标记 token 本身，同句真实出现仍命中）。字段为空 N/A 不扣分。

### D4: tier 判定
`detect_tier`：explicit 优先（optimizer 按 `creative_level>=7` 传入 refined/batch）；无 explicit 时 auto 兜底——图片无 shots/NON-IP/FINAL FRAME 概念，auto 恒判 batch（仅影响直接调用 `evaluate` 的场景，optimizer 路径总是显式传入）。

### D5: 择优接入点与缓存
候选循环后（`num>1` 且 `domain=image`）：`scored = [(evaluate(p, meta, source_prompt=request.prompt, language=lang, tier=tier, max_length=request.max_length)["score"], p) ...]` → 降序 → 最优为 `optimized_prompt`，`candidates` 降序。语言判定：源提示词含中文字符 → zh，否则 en（复用视频保真度的 zh 检测思路）。缓存 key 已含 `num_candidates`，择优不影响缓存正确性。视频 legacy 分支（`is_video`）不接入择优（保持行为不变，见 spec 兼容性）。

### D6: 字段收敛与上限
`excluded_characters`：兼容字符串（按 `[\n;,]+` 分割）与字符串数组（对齐视频契约收敛规则）；上限 20 项。`no_swap_pairs`：仅接受二元组数组（每对恰含两个非空字符串）；上限 10 对。非法形态丢弃 + warning，不抛错。收敛逻辑放 `prompt_engine/api/rest.py` 请求规范化处（对齐视频契约层职责），模型字段保持简单类型。

## Risks / Trade-offs

- [图片 batch 30 词下限可能误伤极短 MJ 风格提示（10-20 词）] → 长度仅占 20/100 权重且下限低；评分用于择优而非硬拒绝，极端短提示仍可当选。
- [择优改变 `num_candidates>1` 的历史输出（主输出可能不再是 candidates[0]）] → 这是择优的预期收益；缓存 key 含 num_candidates 无污染；单候选路径不变，风险面可控。
- [图片/视频评估逻辑双份存在，未来漂移] → 语义对齐注释 + 签名一致，后续可收敛到 `prompt_engine_core`（单独 change）。
- [新字段在非 rest 调用方（SDK/直接构造 request）无收敛] → 模型字段保持 list[str]/list[list[str]] 简单类型；收敛仅限 rest 边界，直接构造调用方自行保证形态（与视频契约一致）。

## Migration Plan

- 部署：纯新增可选能力，`OptimizeRequest` 新字段默认空 → 缺省行为与旧版本一致；无数据迁移。
- 回滚：回退提交即可；缓存无需清理（择优结果 key 含 num_candidates，旧缓存条目与旧行为一致）。

## Open Questions

无（波段数值属实现细节，评审阶段可微调，不影响 spec 行为契约）。
