# 8020 引擎侧落地 Higgsfield P0（evaluator 层级/违规扣分 + 导演字段 + 边界上浮）

## 背景
Multi-Publish 契约层已先行落地（PR #793）：`video-prompt-engine-contract.js` 支持
excluded_characters/no_swap_pairs/color_ratio/shots[]/beats[]/appendVideoTrailer，
精修层 max_length 按后端能力门控（8013→2000 / 8020→4000）。
本次为跨仓库 4.4 联调项：引擎侧（8020 `video_prompt_engine/`）补齐输出与评估机制，
并抬高模型边界，使契约层精修层默认自动上浮至 5000。

## 目标（对应归档 change video-prompt-higgsfield-mechanics task 4.4 a-d + 报告 P0.1-P0.4）
1. 8020 结构化输出新增字段：`excluded_characters[]`、`no_swap_pairs[]`、`color_ratio`
   （默认 60:30:10）、`shots[]`（≤3，含 beats[] ≤6 时间块）——LLM 输出 + post-process 归一
2. evaluator 长度判据层级感知：批量层 en 100-400 词 / 精修层 en 500-5000 词
   （zh 对应字符区间），精修层长模板不再被 -20 硬扣
3. evaluator 违规扣分 `violations[]`：缺席角色出现 / swap 对被替换 / 精修层缺收尾参数行 / 缺 Audio 块
4. `VideoOptimizeRequest.max_length` 边界 4000 → 5000（8020），契约层自动上浮
5. 收尾参数行引擎侧输出：`Photoreal. NON-IP. {aspect}. {duration}s. {audio} only.`（与契约 appendVideoTrailer 模板一致）

## 非目标
- 8013 图片引擎不做字段扩展（其 evaluator 无 100-400 词判据，仅 8020 有）
- P1/P2（模板形态切换/风格词典/失败模式库/资产库）不在本 change

## 实现决策（Claude 双模型分析定案，2026-08-14）
- **仅动 8020**：8013 `prompt_engine/evaluator.py` 无 100-400 词判据（LLM 维度评分），报告表述已修正；8013 models le=2000 不动
- **tier 语义**：explicit（`creative_level≥7` → refined / 否则 batch，optimizer 恒显式传入）优先；auto-detect（shots 非空 / NON-IP / FINAL FRAME）仅在无 explicit（None）时兜底（`detect_tier`，W4 修复：显式 batch 不被 NON-IP 顶回）
- **长度层级**：batch en 100-max(400, max_length//6) 词 / zh 120-2000 字符；refined en min(500, max(150, max_length//6)) ~ max(500, max_length//5) 词 / zh 500-5000 字符（W2 修复：下界随预算缩放，1800 预算下 500 词不可达 → 下界 300，防区间坍缩；提示词同步“随预算缩放”口径）
- **契约常规层默认对齐**（复审 W7）：8020 batch 未显式传 max_length 时由 500 → 1800（对齐 8020 引擎默认，500 字符装不下 batch 层 100 词下界）；8013 保持 500 零回归
- **收尾行**：`Photoreal. NON-IP. {aspect}. {duration}s. {audio} only.`，仅 refined 层；batch 层禁止；幂等（body 含 NON-IP 不重复 append）
- **C6 生命周期**：render body → append 尾行（post_process_video 内、入 evaluator 前）→ body 预算 = max_length − len(tail)，tail 永不截断
- **violations**：缺席角色 -10 / swap 被替换 -10 / refined 缺尾行 -10 / 缺 Audio 块 -5；词边界/整名匹配（单字中文拒绝，防"关"误击"关键"）
- **C1 数据源**：`VideoPromptMeta` 增 `aspect`(默认"16:9")/`audio`(默认"sfx")；duration 用 `int(duration_hint)` 去 .0；`extract_video_meta` 全字段钳制/裁剪（shots≤3/beats≤6/pairs≤5/excluded≤10/color_ratio 正则归一）
- **C2 max_tokens**：`max(3000, max_length*2)` 动态（llm/base.py call 新增 max_length 参数）
- **C4 缓存**：`_cache_key` 前缀版本盐 `HIGGSFIELD_FMT_V1`；新字段全默认值 → 旧缓存可重建
- **C5 同源**：`JSON_RETRY_HINT` 与六策略 Output Format 均从 `VIDEO_OUTPUT_KEYS`（13 键）生成，禁止双份手写
- **C1 引用协议（复审修复）**：契约 `_assertReferenceProtocol` 对声明 excluded_characters/no_swap_pairs 非空时 fail-closed（正文须含 `[ABSENT]`/`<<<>>>`）→ 引擎 system prompt（refined+batch）新增标记指令；evaluator 检查前先剥离标记区段，防合规标记自罚分；契约 `_normalizeNoSwapPairs` 双形态兼容（引擎对象形态 {from,to} → 规范二元组 [from,to]），使 no_swap_pairs 声明真实生效
- **W1 修复**：`_clean_aspect` 正则后限长 ≤10（超长回退 16:9），防 `1920:1080:24` 炸 pydantic；`_clean_color_ratio` 对齐契约 `\d{1,3}:\d{1,3}:\d{1,3}` + ≤20 字符（复审 W3）
- **标记剥离收紧**（复审 C1）：`_strip_reference_markers` 只剥 `[ABSENT]`/`<<<` 标记 + 紧邻一个词，标记后同句真实出现仍扣分（过度剥离会隐藏真实违规）；未闭合 `<<<` 前缀同样处理（契约仅要求 includes）
- **C6 截断正则容错**（复审 W5）：`Photoreal` 缺句点变体尾行也可剥离重 append；真 optimizer 路径超长截断 E2E 测试闭合
- **swap 双形态双向**（复审 W3/W4）：evaluator 读 `[from,to]` 二元组防崩；`_clean_swap_pairs` 接受二元组输入且仅收字符串（数字丢弃，对齐契约）
- **测试**：新增 `tests/test_higgsfield_p0.py`（40 项：models 边界/归一/尾行生命周期/evaluator tier+violations/optimizer 盐与 hint/六策略快照/8013 镜像零改动/T4-T10 + W3-W6 复审回归）
- **遗留（非本 change）**：`tests/test_resources_preview.py::test_resources_has_correct_count` 基线失败（8013 RAG 数据计数 0，与本 change 无关）
