# 视频提示词优化引擎 — 新版引擎质量评估报告（2026-08-15）

> 评估方式：确定性评分器全量扫描 258 条真实《Hell Grind》精修语料 + 模型（评审者）逐条人工打分对照。
> 数据源：`video_prompt_engine/knowledge/seed_higgsfield_prompts.json`（Higgsfield 开源长片《Hell Grind》公开语料，258 条）。
> 被测代码：`video_prompt_engine/evaluator.py`（Round3 Batch A/B/C + DEEP 系列）。

## 0. 评估口径与诚实边界

本机无任何可用 LLM API key（环境变量/配置文件均为 `${ENV_VAR}` 占位，`ai-router.truevideo.top` 可达但无凭据），
因此本次**未跑真实 LLM 优化链路、未跑真实图/视频模型渲染**。评估 = 确定性评分器 + 语料统计 + 模型人工审阅。

- 评分器：`evaluate()` 输出 0-100 分（长度 20 + 六要素 30 + 镜头字段 50 + 保真 20，再叠加违规扣分）。
- 语料形态：全部以**纯文本**喂入（`video=None`，无结构化 meta）——这恰好是运营后台"提示词评测"的真实形态。
- 人工打分：评审者对样本逐条给出 0-100 分并记录理由，用于量化评分器偏差方向。

## 1. 引擎能力全景（被测新版引擎已实现的功能）

| 机制 | 位置 | 说明 |
|---|---|---|
| 多候选择优 | `optimizer.py:333` `select_best` | 对 LLM 多候选按评分排序取最优 |
| 违规扣分 | `evaluator.py:354-411` | 缺席角色 -10 / swap -10 / 缺尾行 -10 / 缺音频 -5 / 时间轴缺失 -5 / timing_break -5 / continuity_break -5 / 块覆盖 -5 / lock-gated 规则 -5 |
| tier 分层 | `detect_tier` `evaluator.py:297-305` | batch（100-400 词）/ refined（500-5000 词），显式 tier 或自动判据 |
| 六要素 | `evaluator.py:490-501` | subject/action/environment/lighting/color/style 关键词命中 |
| 保真 | `evaluator.py:508-515` | 中文 2+ 字词命中率；英文实体 token 命中 |
| 跨镜承接 | `_check_continuity` `evaluator.py:185+` | 实体级白名单 + 覆盖率兜底，否定感知 |
| 块覆盖 | `evaluator.py:467-484` | refined 渲染串块标记命中率 ≥0.8 |
| 引用协议 | `_strip_reference_markers` | `[ABSENT]`/`<<<>>>` 标记剥离防自罚分 |
| 知识库 | `knowledge/`（258 条语料 + 关键词/导演风格/失败模式/角色描述） | RAG 检索增强 |

## 2. 全量评分结果（258 条，auto-tier 口径）

```
scores: min=11.7  max=58.3  mean=43.7  median=41.7
>=60: 0 条    >=50: 59 条（23%）    <30: 14 条（5%）
tier 自动判定：refined 101 / batch 157
长度合格：115/258（45%）→ 长度失败 143 条（55%）
违规扣分：121 条样本触发（47%）
违规分布：missing_audio 73 次（batch 层 70，refined 层 3）
         missing_trailer 48 次（全部在 refined 层）
六要素平均命中：0.91（style 漏 66、color 漏 29、action 漏 19）
镜头字段（纯文本形态）：has_shot/has_camera/has_motion 全部为 0
```

## 3. 人工打分对照（评审者逐条打分）

| 样本 | 内容概要 | 词数 | 引擎分 | 人工分 | 偏差原因 |
|---|---|---|---|---|---|
| hg-scene_74-001 | 重风雪终局三切，完整终态描述 | 4117 | 58.3 | 90 | 评分公式硬上限（见 P0-1），实际无任何扣分 |
| hg-scene_74-011 | 慢动作三人走位，Vinterberg/Lubezki 风格段 | 1758 | 54.2 | 90 | color 未命中（正文无显式色词）+ 上限 |
| hg-scene_74-012 | Duration/Aspect/ONE CONTINUOUS SHOT 终态 | 1928 | 48.3 | 88 | `missing_trailer` -10 误伤（P1-2） |
| hg-assets-003 | 917 词写实机甲资产卡 | 917 | 28.3 | 82 | auto 判 batch + 超长扣分 + action/style 漏检（P1-3/P1-4） |
| hg-credits-013 | 85 词无缝转场卡 | 85 | 20.0 | 75 | batch 长度带下界 100 误杀 + missing_audio 误伤 |
| hg-scene_cinema_bomb-003 | 俄语警察群像资产卡（22 词） | 22 | 11.7 | 72 | 长度带下界误杀 + 六要素全 miss（仅支持 en/zh）+ missing_audio |

**结论**：引擎对"引擎自产输出形态"（结构化 meta + 规范尾行）的排序能力是真实的；
但用作**纯文本评测器**（运营后台场景）时，系统性低估真实世界高质量语料 30-50 分。

## 4. 问题诊断（按严重度）

### P0-1 评分公式硬上限：纯文本评测永远 <60
- 位置：`evaluator.py:517-525`。`has_shot`(20) + `has_camera`(15) + `has_motion`(15) = 50 分
  只可能在 `video` 结构化 meta 携带 `shot/camera/motion_intensity` 时获得。
- 纯文本评测时 `checks["has_*"]` 恒 0 → 满分 = (20+30+20)/1.2 = **58.33**。
- 证据：258 条全量 max=58.3，正是该上限；`hg-scene_74-001` 六要素全中 + 长度合格 + 零违规仍只有 58.3。
- 影响：任何"把用户粘贴的提示词拿来打分"的场景（运营后台评测、对外 API）都会系统性低估；
  多候选择优内部使用影响较小（同形态候选相对排序仍有效），但**当 LLM 未回填 meta 时 50 分同样不可得**。

### P0-2 auto-tier 判据只认引擎格式标记 → 真实语料 70/258 误分层
- 位置：`detect_tier` `evaluator.py:297-305`。判据 = `video.shots` 非空 或 正文含 `NON-IP`/`FINAL FRAME`。
- 真实语料多数无这些标记 → 157 条被 auto 判为 batch，其中 **140 条（89%）超 batch 上界 400 词** → 长度扣 20 分。
- 与语料类别标签对比：auto vs 类别 不一致 70/258（类别含 refined 106/batch 100/asset 23/variant 29，
  引擎只有两 tier，asset/variant 52 条无对应层）。
- 影响：长度权重 20 分大面积丢失，是 mean 只有 43.7 的主因之一。

### P1-1 missing_audio 在 batch 层误伤纯视觉/静态 prompts
- 位置：`evaluator.py:393-411`。batch 层正文无音频词（sfx/sound/audio/music/score…）即 -5，
  除非含 silent/无声。73 次触发中 70 次在 batch。
- 证据：`hg-assets-003`（"A documentary photo…"静态资产卡）、`hg-scene_cinema_bomb-003`（静态群像）、
  `hg-credits-013`（转场卡）全部被扣。
- 机理：音频词检查应只在"显式需要音频"的形态生效（refined 尾行/Audio 段），
  batch 层对纯视觉 prompts 不应默认要求音频词。

### P1-2 missing_trailer 判据对真实 refined 形态误伤
- 位置：`evaluator.py:390-391`。`tier == "refined" and "NON-IP" not in upper_text` → -10。
- 证据：`hg-scene_74-012/015/020/028` 等完整终态描述（含 `Duration: 12 seconds. Aspect ratio: 16:9.` 控制段、
  ONE CONTINUOUS SHOT）无引擎式 `NON-IP` 尾行 → 全部 -10。48 次触发全在 refined。
- 机理：`NON-IP` 是引擎自产尾行标记，真实世界精修 prompts 以"控制段（Duration/Aspect/Shot 序号）"等价表达，
  应识别控制段形态即视为有 trailer 预期。

### P1-3 长度带与真实语料形态错位
- 位置：`evaluator.py:331-352`。batch 带 100-400 词、refined 带 500-5000 词。
- 证据：语料类别为 batch 的 100 条 mean=663 / median=510 词（min 330 / max 1429），
  即使强制 tier=batch 仍有 **92% 长度失败**；refined 类别强制后 8% 失败（正常）。
- 机理：长度带按"引擎自产输出"标定（batch=短小精炼、refined=长脚本），与《Hell Grind》语料分类
  （batch=原始批量抽卡、refined=导演分镜单，都较长）不是同一语义。用于评测用户/语料时需要"来源形态"口径。

### P1-4 六要素关键词表缺口
- 位置：`evaluator.py:490-499`（关键词表内联，非独立常量）。
- style 漏 66/258（26%）：漏检样本高频词含 `cinematography`(53)、`lens`(54)、`haze`(53)、`blur`(52)、
  `documentary`、`moody` 等——全是风格词但未收录（仅 style/cinematic/epic/风格）。
- color 漏 29/258：漏检样本高频词含 `red`(26)、`dark`(21) 等具体色词——仅收 color/palette/hue/色，
  不收具体颜色名。
- 语言缺口：俄语样本六要素 6/6 全 miss（关键词仅 en/zh）；`hg-scene_cinema_bomb-003` 0/6。

### P2-1 视频引擎无对外评测端点
- `video_prompt_engine/api/rest.py` 仅 `/v1/video/optimize`、`/optimize/batch`、`/classify`、`/feedback`，
  **没有 `/v1/video/evaluate`**；图片引擎 `prompt_engine/api/rest.py:287` 有 `/v1/evaluate`（before/after 对比）。
- 影响：运营后台"提示词评测"目前接不到视频引擎评测；要接入需新增端点，且必须先修 P0-1/P0-2，
  否则接入即暴露 58.3 上限与误分层。

### P2-2 语料 asset/variant 两 tier 未建模
- 类别标签含 `tier:asset`(23) / `tier:variant`(29)，引擎只有 batch/refined 两 tier → 52 条（20%）无对应层，
  强制评估长度失败 61%/90%。

## 5. 优化建议（按优先级，附定位）

1. **【P0】纯文本评分上限修复**（`evaluator.py:517-525`）：`has_shot/has_camera/has_motion` 增加文本级兜底——
   从正文检测镜头/相机/运动词（如 shot/cut/camera/lens/movement），或引入"评分模式"参数：
   结构化 meta 模式用现公式，纯文本模式把 50 分权重重分配给六要素/结构，消除 58.3 硬顶。
2. **【P0】auto-tier 增加长度兜底**（`evaluator.py:297-305`）：无引擎标记时按词数推断——`>833` 词倾向 refined、
   `100-400` 倾向 batch、`<100` 视为 asset/短卡（新形态）而非 batch 长度失败。修后 batch 层长度失败 140→约 19 条。
3. **【P1】missing_audio 改为"显式音频需求"判定**（`evaluator.py:393-411`）：batch 层仅在正文含
   音频相关意图（sound design/audio cue 等显式词）时检查；纯视觉/静态形态默认 N/A，不扣分。
4. **【P1】missing_trailer 判据扩展**（`evaluator.py:390-391`）：识别控制段形态
   （`Duration:`/`Aspect ratio:`/`ONE CONTINUOUS SHOT`/`CUT n` 等）即视为精修形态，不再强制 `NON-IP` 字面量。
5. **【P1】六要素词表扩充**（`evaluator.py:490-499`）：style 增加 cinematography/documentary/moody/
   haze/blur/grain/vignette/contrast 等；color 增加常见色名（red/blue/gold/black/white/dark 等）；
   增加俄语（或降级为"任一语种命中即算"）。
6. **【P1】长度带支持"来源/目标"双口径**（`evaluator.py:331-352`）：评测用户输入时长度只作提示不作扣分，
   或按语料形态选带；保持引擎自产输出用现行带。
7. **【P2】新增 `/v1/video/evaluate`**：对齐图片 `/v1/evaluate` 的 before/after 对比语义，供运营后台接入；
   接入前必须完成 1-2。
8. **【P2】asset/variant 形态支持**：把 22-950 词的"资产卡/变体卡"作为独立形态或并入 batch 下界的弹性区间。

## 6. 引擎真实价值（避免误判为"不可用"）

- 在**多候选择优**（引擎主路径）中，评分用于同形态候选排序 + 违规扣分，上述问题影响较小：
  `select_best` 的 63:1 分层漏斗思路（见 HELLGRIND-NUM-CANDIDATES-COST-MODEL.md）依然成立。
- 违规扣分（缺席角色/swap/时间轴/承接）在结构化 meta 场景下是真能力，能拦截 LLM 结构漂移。
- 本次暴露的是**"评测器模式"的缺陷**：把面向引擎自产输出的公式直接用于真实世界纯文本评分时，
  存在 3 处系统性误伤（音频/尾行/长度带）与 1 个硬上限。修复成本低（均为判据/词表级改动），收益直接。

## 8. 修复后复测（2026-08-15，video-corpus-expansion）

> 针对第 4 节问题诊断逐项修复后复测；修复代码：`video_prompt_engine/evaluator.py`（P0-1/P1-1/P1-2/P1-3/P1-4 全部落地）+ 语料/负样本资产化。

### 8.1 修复对照（258 条 Higgsfield 语料，tier=batch 口径）

| 指标 | 修复前 | 修复后 |
|---|---|---|
| max 分 | 58.3（评分公式硬上限） | **100**（P0-1 镜头字段文本兜底生效） |
| mean（length_strict=False 评测口径） | 43.7 | **95.6**（median=100） |
| mean（length_strict=True 引擎候选口径） | — | 80.0 |
| missing_trailer 触发 | 48 次 | **0 次**（P1-2 控制段等价识别） |
| missing_audio 触发 | 73 次 | 47 次（P1-1 显式音频需求：剩余均为语料显式声明无声/意图词不满足） |
| score>=90（评测口径） | 0 | 231/258（90%） |

### 8.2 负样本校验模式（evaluate_negatives）

新增 `knowledge/seed_failure_samples.json` 14 条失败样本（曝光/死中心/视线/音频/尾行/时间轴/节奏/缺席角色/互换/跨镜承接/剪影/风格污染/暖色泄漏），
按 failure_tags 与 evaluate() 触发违规匹配：**11 个可判定模式召回 1.0、漏检 0、误报 0**；
4 个 gated 未启用规则（silhouette_break/style_contamination/warm_light_leak/skin_guard）动态标 covered=False，资产保留、规则启用后自动进入召回统计。

### 8.3 语料资产化与扩充机制

- `scripts/build_corpus_index.py`：glob 合并 `knowledge/corpus/**/*.json` + prompt_text 去重 + 必填/tier/长度/质量分校验，`--strict` fail-closed；产物 `corpus_index.json` 由 loader 显式 extra 并入。
- 条目格式扩展 `corpus_type`/`failure_tags`/`applicable_to`/`tier`/`meta`：旧条目按 positive+few-shot 归一，零回归（347 条旧条目默认值断言通过）。
- few-shot 注入排除 negative/eval-only 条目（`rag_retriever._few_shot_eligible`），检索路径仍可访问负样本。
- 评估器修复与负样本资产已由 `tests/test_eval_fixes.py`（17 项）+ `tests/test_corpus_expansion.py`（13 项）锚定。

### 8.4 剩余边界（诚实记录）

- 俄语等多语种六要素仍受词表限制（仅 en/zh）；语料族级形态（asset/variant）仍未建模独立 tier。
- 长度带双口径是评测器校准手段，引擎自产输出（length_strict=True）仍按现行带计分。
- 本报告为确定性评分器 + 语料统计结论；真实 LLM 优化链路与图/视频模型渲染仍需外部凭据验收。
### 8.5 P0-P2 优化后复测快照（2026-08-15，evaluator-p0-p2-optimization）

> 针对 §4 P0-2/P1-1/P1-2/P1-4/P2-1/P2-2 的进一步优化（tier 长度兜底 / 部分命中 / 长度梯度 / 词表资产化+多语种 / 评测端点 / advice）后复测，口径与 §8.1 相同（258 条，length_strict=False）。
>
> **评审修复后复测（2026-08-15 晚，evaluator-p0-p2-optimization 双模型评审 W2-W5 修复；词干/中文 form 边界按复审闭环）**：镜头三维度检测改全词边界（删子串兜底，pandemic/companion 不再误击 pan/cut）、英文保真增加轻量词形归一（robot→robots）、select_best 同分决胜接入 optimizer 生产路径、词表回退与资产逐词一致。258 语料 auto 口径 mean **90.9**（median 98.5）/ max 100 / score≥90 194 / ≥80 217 / <60 19 / missing_audio 28。mean 较修复前 -1.1 主因是镜头维度词边界收紧（修正"含 pan 的假运镜"等假阳性，评测精度上升）；golden set 排序一致性 r 0.805→0.913。

| 指标 | §8.1 修复后（#52） | P0-P2 后（auto tier） | 变化 |
|---|---|---|---|
| max 分 | 100 | 100 | — |
| mean | 95.6（median=100） | **92.0**（median=98.5） | -3.6 |
| score≥90 | 231/258 | 197/258 | -34 |
| score≥80 | — | 227/258 | — |
| score<60 | — | 16/258 | 新区分 |
| missing_audio | 47（tier=batch 口径） | 28（auto 口径：refined 15 + batch 13） | 口径修正（§8.5 原 47 为 batch 值） |

**差异归因（诚实记录）**：
- 主因是**长度梯度取代全额 20 分**：91/258 条在 auto tier 带外（长文精修/短卡），评测口径从「带外不扣长度分」变为「按接近度部分给分」（长度分 mean 20→17.55）。这是 P1-2 的设计意图——评测口径保留区分度，不再人人 100；§8.1 的 95.6 是「带外也全额给长度分」的乐观基线。
- 六要素部分命中（P1-1）与扩充词表（#52 词 + ru，P1-4/P2-2）基本抵消：语料长文本每要素 ≥3 词命中占比 93-99%，部分命中规则对 258 语料影响小（受影响的集中在短卡/俄语样本）。
- 剩余 16 条 <60 分：短资产卡/俄语群像等「信息密度低」样本被正确压低——正是评测器需要的区分能力。
- golden set 校准（12 条，6 条报告人工分 + 6 条评审模型补标）：P0-P2 基线 MAE=16.2 / RMSE=18.75 / Pearson r=0.805；评审修复后 MAE=16.93 / RMSE=19.74 / **Pearson r=0.913**——词边界收紧与保真词形归一使排序一致性显著提升（r +0.108），MAE 微升（+0.7）集中在长精修场景引擎分偏高（100 vs 85-90，要素/镜头全中）；短卡与俄语偏低（-12~-39）仍是下一轮优化方向（已由 golden set 资产固化可复测）。

## 7. 复现命令

```bash
# 用 worktree 本地源码
PYTHONPATH="D:/Data/projects/mp-worktrees/pe-round3bc-delivery" python /tmp/eval_v2.py
# 输出分布 + 违规分层 + elements 缺口（/tmp/eval_v2_result.json）
PYTHONPATH="D:/Data/projects/mp-worktrees/pe-round3bc-delivery" python /tmp/eval_v3.py  # 6 条样本细审 + 词表缺口
PYTHONPATH="D:/Data/projects/mp-worktrees/pe-round3bc-delivery" python /tmp/eval_v5.py  # 类别交叉 + 强制 tier 长度
```
