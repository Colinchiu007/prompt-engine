# 评估器 round3：zh/ru 长度兜底 / CJK 单字词表 / 258 哨兵入库 / 正则缓存 / 镜头 instrumentation / 无 source 缩放封顶

## Why

2026-08-16 双模型分析（Claude 实测核验，antigravity 地区不可用已降级记录；`analysis-claude.md`）确认 PR #55/#56 落地后仍存在以下缺口：

- **zh/ru 字符刻度长度兜底缺失**：`detect_tier` 词数兜底按空格切分（`count_words`），中文无空格 → 长中文无引擎标记恒判 batch（长度 0 分）；且 refined 层 `missing_audio` 只认拉丁音频意图词，中文/俄语精修样本转 refined 后恒 -5（evaluator.py:595 / :653-662 / :797）。
- **CJK 单字词表纯误击**：zh 词表 v2 含单字（色/光/金/景/立/持/望/战），子串匹配导致「角色」误中 color、「曝光时光」误中 lighting、「金属」误中 color、「中景/远景」误中 environment——5 条 zh 语料实测 8 组单字命中大多为误击，elements_score 被污染（0.778 中 ~0.056 为误击所得）。
- **258 哨兵脚本未入库**：复测脚本只在 `D:\Temp\retest_258.py`，且语言判定只分 zh/en（3 条 ru 被当 en 按词数刻度评分——已知缺陷）；无 CI 门禁，基线漂移不可感知。
- **正则每次调用 re.compile**：`_WORD_BOUNDARY_RE`（evaluator.py:38）/`_CYRILLIC_BOUNDARY_RE`（evaluator.py:46）无缓存，一次 evaluate 数百次编译，258 复测 ~2 分钟主因之一。
- **镜头三布尔无梯度 + 词表歧义**：`has_shot` 仅布尔，且 `_TXT_SHOT`（evaluator.py:939）混入运镜词（pan/tracking/zoom）；裸 still/wide/extreme/摇 在分档场景有污染风险（"still alive"/"extreme wide"/摇晃）。
- **无 source 白送 fidelity 20 分**：golden 7/12 条封顶 100（无 source 时 fidelity 恒 20），黄金集区分度塌陷；但 5 条短卡/俄语样本偏低（Δ=-20~-32，占 MAE 58%）依赖这 20 分保地板——**不能简单移除或重分配**。

## What Changes

### P0（接入前必做）
- **P0-1 zh/ru 字符刻度长度兜底（联动）**：`detect_tier` 增 `language="en"` 参数（向后兼容默认）；zh/ru 路径 `len(prompt) > 2000 → refined`（与 zh/ru batch 带上界 2000 联动，evaluator.py:686，杜绝重蹈 500-833 双亏区）；`length_fallback`/`tier_auto="length"`/`trailer_waiver` 三处同步并入（evaluator.py:653-662）。**耦合修**：refined 层 missing_audio 判定补 zh 音频意图词（音效/环境声/雨声/配乐/旁白/对话/音乐）与 ru 音频词（звук/музыка/речь/голос/диалог）。
- **P0-2 CJK 单字词表 v3→v4（去单字 + 合成词扩充 + 动作形态补全）**：zh 六要素去全部单字，subject 保留「人」为刻意例外；action/environment/lighting/color 补合成词表（见 design.md 完整清单：奔跑/战斗/行走/站立/凝视/室内/城市/背景/光线/阳光/红色/金色/黑色…）；`element_keywords.json` version 2→3→4（评审 W2 补高频动作形态 走着/走起/走来/跑去/跑来/挥手/望着/坐着/看着/站住/站定，JSON 与 knowledge.py fallback 同步；`_asset_fingerprint` 自动感知）。实测 v3 基线 elements_score 0.778→0.722（max -1.4 分），损失全为误击剔除；golden 与 258 四指标在 v4 复测零回归。
- **P0-3 258 哨兵脚本入库 + CI 独立 step**：新增 `scripts/eval_corpus_258.py`——固定路径读 `seed_higgsfield_prompts.json`（断言 total==258）、**三路语言判定**（复用 evaluator 共享 `detect_lang`：CJK→zh / Cyrillic→ru / else en）、输出 n/mean/median/≥90/≥80/<60/missing_audio、`--json`、退出码 0/1/2（输入损坏返回 2）；`.github/workflows/test.yml` 独立 step（`timeout-minutes: 10`；评审 C1 将 job 级超时 5→15 分钟，step 上限不再被 job 罩死）。首版门禁先宽后紧：mean≥88.0 / ge90≥190 / lt60≤30 / missing_audio≤40（round3 落地重定基后再收紧）。

### P1（区分度与工程化）
- **P1-1 正则缓存**：`functools.lru_cache(maxsize=2048)` 包两个工厂函数；缓存键仅 token（str），hashable + 线程安全；maxsize 设上限防动态 token（跨镜承接/角色名）无界膨胀。零分数影响，258 复测 bit-identical。
- **P1-2 镜头分型 instrumentation（零分数影响）**：`checks["shot_types"]/["shot_type_count"]/["camera_types"]/["motion_types"]` 输出 distinct 景别/机位/运动型（保守词表，禁裸 still/wide/extreme/摇；运镜型归 motion 不归 shot；否定感知 "no rotation" 不计数）。**分数梯度缓行**：0/10/20 全梯度实测恶化 golden MAE（15.77→16.46，hg-assets-003 校准正中被砍 10 分）；golden 12 条不足以证伪梯度，本轮不做分数切换，instrumentation 供 round4 数据驱动决策。

### P2（能力与健壮性）
- **P2-1 无 source 缩放封顶**：`score = min(score, 90 + 7*elements_score)`（无 source 时，≤97）；有 source 时 ceiling 仍 100。实测 golden MAE 15.77→**14.85**（r 0.915→0.920），7 条封顶样本恢复区分度（不再顶格 100，分布在 95.8-97.0，elem=1.0 样本恰落 97 封顶），短卡地板不塌（A/C 三案实测恶化 18.78/20.43/19.83 故弃）；258 重定基 mean 92.3→91.0（设计意图）、ge90 213→216、missing_audio 25→20。
- **P2-2 en 短卡词表顺带扩充**（与 P2-1 地板联动，可选小步）：`demon/painting/illustration/orb/hellscape` 等 golden 短卡关键缺口词。

## Capabilities

### New Capabilities
- 无（归入既有 `video-prompt-engine` 规格）

### Modified Capabilities
- `video-prompt-engine`：扩展「评估与择优机制」——zh/ru 字符刻度长度兜底（联动 batch 上界 + trailer 豁免 + 双语音频意图词）、CJK 合成词词表、镜头/机位/运动分型 instrumentation、无 source 缩放封顶（100 保留给保真已验证）；扩展「知识库资产」（element_keywords zh v3 + en 短卡补充）；新增「语料哨兵门禁」（scripts/eval_corpus_258.py + CI 独立 step）。

## Impact

- 文件：`video_prompt_engine/evaluator.py`、`video_prompt_engine/models.py`（language 缺省自动判定）、`video_prompt_engine/api/rest.py`（逐条 detect_lang）、`prompt_engine_core/knowledge/element_keywords.json` + `prompt_engine_core/knowledge.py`（fallback 同步）、新增 `scripts/eval_corpus_258.py`、`.github/workflows/test.yml`（job 超时 15 分钟）、新增 `tests/test_evaluator_p0p2_round3.py`、`openspec/specs/video-prompt-engine/spec.md`
- 测试：round3 用例（zh 长度兜底 + 单字反例 + 动作形态召回 + 哨兵注入回归 + 正则缓存 + 镜头分型 + 分句否定 + 封顶/地板快照 + 评审修复回归 ≈ 40 项）+ 全量回归（947 基线）+ golden 复测 + 258 复测双门禁
- 兼容性：`detect_tier` 新增 language 参数（默认 en 向后兼容，入口归一化 zh-CN→zh）；`checks` 增 shot/camera/motion_types 增量字段；`elements_score` 双重使用（主公式 + ceiling 缩放）在 docstring 注明；`/v1/video/evaluate` 未传 language 时行为由「默认 en」变更为「按正文自动判定」（仅对含 CJK/西里尔的请求生效，显式传 language 不受影响）；violations/score 顶层结构不变
- 共享资产跨界（评审 I7）：`element_keywords.json` 同时被图片引擎消费（`prompt_engine/evaluator.py:282`），zh 词表 v3 去单字 + v4 动作形态扩充会静默改变图片引擎中文要素分（消误击 + 提召回）；全量测试已含图片侧用例无回归，图片侧 golden 建议后续独立复核
- 评分分布变化面：zh 样本 -0.03（P0-2）/ +0.1（P0-1）；无 source 样本 mean -1.7~-2.7（P2-1，重定基）；en/ru 零影响（P0-1/2）；258 哨兵门槛先宽后紧
- 实施批次：A（4/3/5 instrumentation，零分数影响）→ B（2/1，分数微调）→ C（6，封顶重定基）；跨项验收 = 258 四指标（重定基）与 golden（MAE≤15.77 且封顶样本两两可分）双绿；`evaluator_version` v0.11→v0.12
