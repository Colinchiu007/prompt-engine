# 评估器 P0-P2 深水区优化（跨语言保真 / 中文名字边界 / 违规量化 / 版本指纹 / 阈值联动 / 词边界手术式 / 正确性 / RU 词表）

## Why

2026-08-16 双模型分析（Claude 实测核验；antigravity 地区不可用已降级记录）确认 PR #54 落地后仍存在以下缺口：

- **跨语言保真盲区**：中文 source → 英文 prompt 时 `fidelity` 恒 0（`zh_chars` 2-gram 在英文正文全 miss），20 分项恒丢，忠实翻译与乱写无区分度——中文用户（源提示词中文、引擎输出英文）的核心场景。
- **中文名字子串误击**：`_contains_word` 词边界正则只保护拉丁字符，excluded 角色「林晓」命中正文「林晓雨」→ 误扣 -10；涉及 excluded/swap/continuity/gated 四条路径。
- **违规拍平**：`timing_break` 无论 1 个 beat 超 0.1s 还是 10 个 beat 超 30s 都是 -5（dict 键覆盖）；`block_coverage` ratio 只在 checks、不进违规明细；`select_best` tie-break 按违规**类型数**而非惩罚量（1 个 -10 与 2 个 -5 同权重）。
- **无版本指纹**：`evaluate()` 返回无 `evaluator_version`/资产 hash，运营后台跨版本评测结果不可比；rest.py:181 硬编码 `v0.10-deterministic` 与 evaluator 双处漂移。
- **阈值双处硬编码**：`detect_tier` 的 833（evaluator.py:336）与 batch 上界 `min(max(400, max_length//6), 833)`（evaluator.py:399-401）不联动——500-833 词无标记文本判 batch 且长度扣分（双亏区）。
- **六要素子串误击**：`t in lower` 子串匹配（evaluator.py:577），短英文词 red/sun/hot 误击 category/sunrise/hotel。
- **剥离参数不一致（正确性）**：`_strip_reference_markers` 在 evaluate() 主路径（433）带 reference_names 调用，但 `_check_continuity`（227）与 `_apply_gated_rules`（305）不带名字调用——`[ABSENT] Roko` 中的 Roko 在 continuity/gated 路径残留，声明缺席的角色被计为在场。
- **RU 词表缺口**：golden ru 样本（hg-scene_cinema_bomb-003）полицейских/серой/однотонном/фоне 全不在 RU 词表，六要素全 miss（黄金集误差主源之一）。
- **空输入无契约**：`evaluate("")` 实测返回 16.7 分（fidelity 白送 20 分），API 层 422 但引擎内部无显式契约。
- **全量权重校准被阻塞**：golden 12 条中 7 条=100 分封顶（无 source fidelity 白送 20 + 三布尔镜头 + 六要素全中），在 5 条可导样本上拟合 6 个权重 = 过拟合。本轮落地**门禁 + 诊断工具**，全量搜索列为 next change（前置：封顶拆解）。

## What Changes

### P0（接入前必做）
- **P0-1 跨语言保真（门控）**：新增 `_detect_translation_mode(source, prompt)`（source 含 CJK 且 prompt 无 CJK，或反之）；翻译模式下 `fidelity` 走 `_cross_lingual_fidelity` = 0.5×要素跨语言守恒（element_keywords 中英映射命中）+ 0.3×镜头结构保留（shot/camera/motion 在 source 与 prompt 的共现）+ 0.2×长度比 min(src/prompt, prompt/src)。仅门控新路径，en→en / zh→zh 零影响。
- **P0-2 中文名字边界**：新增 `_contains_name(text, token, known_names)`——CJK token 命中位置被更长已知名字覆盖时跳过（「林晓」⊂「林晓雨」）；excluded/swap/continuity 角色名走名字语义，泛词路径（posture/gated）维持现状。抽 `_WORD_BOUNDARY_RE(token)` 单一来源（合并 18-30 与 139-148 双处正则）。
- **P0-3 违规分级量化**：顶层 `violations` 保持 `dict[str, int]`（兼容 ≈40 处测试断言与计分），新增 `checks["violations_detail"]`（每违规键 `{penalty, count, detail}`）；`timing_break` 累计 beat_count/max_diff；`block_coverage` ratio 入 detail；`select_best`/optimizer tie-break 由违规类型数升级为 `sum(abs(penalty))`（同分决胜语义更合理）。
- **P0-4 校准门禁与工具**：CI golden 门禁（pytest 断言 r≥0.90 / MAE≤18 / 258 复测 mean、score≥90 占比哨兵）；`scripts/eval_golden_set.py` 新增 `--scan-weights` 诊断模式（±20% 步进输出热力图，不自动改权重）；全量权重搜索暂缓原因写入 PRD。

### P1（区分度与工程化）
- **P1-1 六要素词边界（手术式）**：element 命中对拉丁词（en）改用词边界匹配（防 red→category），CJK/西里尔词保持子串（中文无空格、俄语词表新补不宜再动）；不引入全局开关。
- **P1-2 detect_tier 阈值单一来源**：新增 `_batch_hi(max_length)` 单一函数；`detect_tier` 的 refined 长度兜底阈值 = `_batch_hi`（不再硬编码 833）；auto 长度兜底进 refined 时豁免 `missing_trailer`（trailer 豁免联动，防 600 词改判 refined 后分数反而下降）。
- **P1-3 版本指纹**：`_EVALUATOR_VERSION = "v0.11-deterministic"` 常量 + `_asset_fingerprint()`（sha256 element_keywords/refined_blocks/golden_set，模块级缓存）；`evaluate()` 返回 `evaluator_version`/`assets`；rest.py meta 复用常量（消除双处漂移）。
- **P1-4 `select_best_detailed`**：`select_best(..., detail=False)` 不变；`detail=True` 返回 `(prompt, meta, score, candidates_info)`（每候选 checks/violations/advice 明细，供运营解释「为什么选它」）。
- **P1-5 剥离去重（正确性）**：evaluate() 单次剥离 `body_text` + reference_names 后下传 `_check_continuity`/`_apply_gated_rules`，删除内部重复调用与参数不一致。

### P2（能力与健壮性）
- **P2-1 advice 严重度排序**：`_build_advice` 违规建议按 penalty 绝对值降序，再排缺失要素/镜头。
- **P2-2 RU 词表补齐**：人工审校进 `element_keywords.json`：subject+полицейский/мужчина/женщина/группа、color+серый/однотонный、environment+фон（golden ru 样本缺词）；TF-IDF 自动扩表列为后续（防泛词稀释）。
- **P2-3 空输入契约**：空/纯空白 prompt → `score=0`、`checks["empty"]=True`、advice 明示；API 层保持 422。
- **P2-4 缓存线程安全**：`_GATED_RULES_CACHE` 用加载哨兵/lru_cache 语义替换裸 dict 判空。
- **P2-5 中文保真轻量归一**：zh→zh 2-gram 匹配前去「了/着/在/的/和/与」等高频虚字后再匹配，容忍近义改写（奔跑→跑步 仍属盲区，记录 PRD 边界）。

## Capabilities

### New Capabilities
- 无（归入既有 `video-prompt-engine` 规格）

### Modified Capabilities
- `video-prompt-engine`：扩展「评估与择优机制」需求——跨语言保真（门控）、中文名字边界、违规量化明细、版本指纹、阈值单一来源、词边界手术式、空输入契约、剥离正确性；扩展「知识库资产」（element_keywords RU 补齐）。

## Impact

- 文件：`video_prompt_engine/evaluator.py`、`video_prompt_engine/api/rest.py`、`video_prompt_engine/optimizer.py`、`prompt_engine_core/knowledge/element_keywords.json`、`scripts/eval_golden_set.py`、新增 `tests/test_evaluator_p0p2_round2.py`、`openspec/specs/video-prompt-engine/spec.md`
- 测试：新增 round2 用例（预估 30-40 项）+ 全量回归；258 语料复测 + golden 复测双门禁
- 兼容性：`violations_detail`/`evaluator_version`/`assets` 为增量字段；`violations` 顶层结构与计分不变；分数分布变化面（P0-2 中文样本上行、P1-2 400-833 区间改判、P2-2 ru 上行、P2-5 zh 上行）经双复测验收
