# Prompt 优化引擎技术亮点与用户价值全景（2026-08-14）

> **文档基线**: prompt-engine `origin/main @ 85ff485`（2026-08-14，Higgsfield P0/P1/P2 全部合入）+ Multi-Publish 契约层 `main @ 87e25fd9`
> **覆盖范围**: 图片提示词引擎（`prompt_engine/`）、视频提示词引擎（`video_prompt_engine/`，8020 独立引擎）、共享内核（`prompt_engine_core/`）、桌面端契约层
> **测试基线**: 全量 654 passed / 3 skipped；本文档所有性能与测试数据均来自合并时的实测记录

---

## 一、引擎全景架构

系统由四个层次组成，遵循"共享内核、领域分离"的架构决策（图片与视频引擎**不拆开**，共用同一内核，领域逻辑各自独立）：

```
┌─────────────────────────────────────────────────────────────┐
│ Multi-Publish 桌面端契约层（video-prompt-engine-contract.js） │  ← 字段收敛 / 校验 / 平台画像 / 尾行模板
├───────────────────────────────┬─────────────────────────────┤
│ 图片引擎 prompt_engine/        │ 视频引擎 video_prompt_engine/│  ← 领域策略 + 领域评估
│  · 7 平台策略 + 分镜策略        │  · 6 平台策略               │
│  · 风格分类 / RAG / 模板直出    │  · Higgsfield 三件套        │
│  · 多候选 / 对比评估 / 反馈闭环  │  · 导演词典 / 角色卡 / 语料  │
├───────────────────────────────┴─────────────────────────────┤
│ 共享内核 prompt_engine_core/（TF-IDF 向量库/注册器/原子写/    │
│  文本清洗/LLM 封装/种子加载）                                 │
└─────────────────────────────────────────────────────────────┘
```

**统一数据流**：请求 → 双级缓存命中检查 → 平台策略选择 → system prompt 构建（风格/层级/上下文/关键词/RAG few-shot）→ LLM 调用（多候选 + JSON 重试）→ 后处理（结构化/截断/尾行）→ 多候选择优 → 缓存写入 → 反馈闭环沉淀。

---

## 二、共享内核 prompt_engine_core（两引擎的公共底座）

### 2.1 TF-IDF 向量检索：预计算索引（性能提升 7000 倍）
- **问题**：旧实现每次查询对每篇文档重复 tokenize + 计算 df，140 条种子实测 **119 秒/查询**（O(n²·len)）。
- **解法**：构建期一次性预计算文档词项计数、df、范数（O(total_tokens)），查询期仅算查询向量 + 余弦（**17ms**）。
- **版本化持久化**：`index.json` v2 格式（`{version, docs}`），兼容历史裸列表格式；加载时自动识别旧格式并告警"陈旧索引需重建"。
- **冷启动硬化**：`_ensure_index()` 把首次检索 ~1.5s 的成本移到进程启动，避免首请求卡顿。
- **验证**：300 次 fuzz 新旧实现逐位一致。

### 2.2 其他共享模块
| 模块 | 能力 | 收益 |
|---|---|---|
| `registry.py` | 泛型策略注册器，**保持注册插入序** | 图片/视频策略注册语义一致，列表顺序可预期 |
| `text.py` | 文本清洗、`<think>` 推理块剥离 | 推理模型输出不会污染最终提示词 |
| `atomic.py` | 文件原子写 | 反馈/状态落盘不产生半截文件 |
| `llm.py` | LLM provider 统一封装（16384 cap） | 超长输出被截断保护，防 token 爆炸 |
| `knowledge.py` | 种子条目/关键词加载骨架 | 两引擎共用解析逻辑，领域模型各自保留 |

---

## 三、图片引擎 prompt_engine

### 3.1 多平台策略
7 个平台策略 + 1 个分镜策略，同一创意一键适配各平台最佳写法：
- **midjourney / stable_diffusion / dalle / tongyi（通义万相）/ yizhang（文心一格）/ jimeng（即梦）/ generic** + **xiaohei_storyboard（小黑分镜）**

### 3.2 核心功能清单
1. **风格自动分类（25 类 MJ 风格体系）**：三级流水线 `keyword_match → vector_rag → llm_classify`（顺序不可更改），自动检测提示词风格并注入对应风格关键词。
2. **RAG few-shot 检索**：种子库向量检索（platform 过滤）+ 关键词命中兜底，给 LLM 注入最相似的优质示例。
3. **双级缓存**（内存 + SQLite）：key = `platform|prompt|creative_level|max_length|negative_prompt|num_candidates`，重复请求零 LLM 调用。
4. **模板直出**：`creative_level ≤ 3` 时免 LLM，直接用模板渲染（省时省钱，适合批量粗出）。
5. **多候选生成**：`num_candidates` 1-5，A/B 测试对比。
6. **上下文注入**：`context`（synopsis/character/setting/character_list）注入角色一致性信息；未知键白名单校验（丢弃 + warning，不改变行为）。
7. **专业工具链**：DSL 解析、prompt 重写（rewrite，含 `<cfg:>` 提取）、扰动变体（disturb）、反向工程（reverse）、中英翻译。
8. **LLM 对比评估**（compare 模式）：5 维 before/after（清晰度/具体度/创意度/可执行性/平台最佳实践），LLM 不可用时兜底评分。
9. **反馈闭环**：好/坏反馈落库（原子写）+ 统计聚合，用户反馈可反哺种子库。
10. **KeyRouter 动态路由**：多 API Key 场景按可用性/配额动态选择 provider。
11. **MCP 服务**：内置 `mcp_server.py`，可被 AI 客户端以 MCP 协议直接调用。

### 3.3 API 端点
`POST /v1/optimize`、`POST /v1/optimize/batch`、`POST /v1/reverse`、`POST /v1/rewrite`、`POST /v1/disturb-optimize`、`POST /v1/classify`、`GET /v1/styles/categories`、`POST /v1/feedback`、`GET /v1/feedback/stats`、`GET /v1/feedback/recent`、`GET /v1/platforms`、`GET /health`

---

## 四、视频引擎 video_prompt_engine（8020 独立引擎）

### 4.1 平台策略
**kling（可灵）/ veo（Veo）/ seedance（即梦视频）/ doubao（豆包）/ hailuo（海螺）/ generic_video** 六类策略，各平台输出格式、约束、语言偏好独立。

### 4.2 Higgsfield 机制（P0/P1/P2 已全部落地）

**P0 · 评估与约束机制**
1. **违规扣分制（violations）**：评估时按规则扣分——缺席角色 `-10`、被禁替换源出现 `-10`、精修层缺收尾行 `-10`、缺 Audio 块 `-5`；`[ABSENT]`/`<<<>>>` 引用协议标记先剥离再匹配，**合规输出不会自罚分**；中英文词边界/整名匹配，中文"关"不会误击"关键"。
2. **tier 层级长度判据**：`creative_level ≥ 7` → refined（精修）层，否则 batch（批量）层；batch 100-400 词 / refined 500-5,000 词（词数刻度），refined 下界随小预算自适应收缩，上界与 `max_length` 联动并封顶——**导演级长模板不再被旧判据误杀**。
3. **双向约束字段**：`excluded_characters`（缺席角色）/ `no_swap_pairs`（禁止 A↔B 替换）/ `color_ratio`（三段配色比）+ `shots[]/beats[]` 时间块（≤3 切、每切 ≤6 beats）。
4. **收尾参数行**：`FINAL FRAME` 终态（位置/姿势/灯光/机位/禁文字）+ `NON-IP` + Audio；尾行生命周期硬化——body 预算 = `max_length − 尾行长`，**尾行永不截断**，超长时剥离漂移尾行重新规范追加。
5. **多候选择优（select_best）**：`num_candidates > 1` 时逐候选评分降序，最高分作为主输出、候选列表按分数排序返回。

**P1 · 知识资产**
6. **导演风格词典**：`director_styles.json` **17 位导演/摄影指导**（如 Lubezki/Deakins），system prompt 注入 `## Director Style Reference`——用户写"暗黑写实"即自动获得对应视觉语言参考。
7. **角色描述符资产库**：`character_descriptors.json` **8 张 Assets 级角色卡**（对标 Higgsfield 资产层 1KB 描述符），`## Character Reference Library` 注入，跨镜头角色一致性有据可依。
8. **失败模式闭环**：`failure_patterns.json` **12 条失败规则**（身份/服装漂移、重复角色、解剖错误、背景渗色、光影漂移、多余文字/水印等）+ feedback `failure_stats` 采集——只列"本镜头可能发生的失败"，不堆模型无视的绝对否定词（plausible negative）。

**P2 · 语料与性能**
9. **全量语料资产化**：`seed_higgsfield_prompts.json` **258 条**（590 条去重，来自《Hell Grind》开源项目公开语料）+ 既有 140 条种子 = **398 条语料**；幂等重建脚本 + loader 合并加载（lru_cache，3MB 语料多实例共享一次解析）。
10. **few-shot 预算硬化**：预算即第二重截断下限、取消"3 条硬上限"、预算计数含标题/围栏——注入内容始终不超预算、不注水。
11. **抽卡成本模型**：`HELLGRIND-NUM-CANDIDATES-COST-MODEL.md`——基于 63:1 分层漏斗实证，**batch 层 3-5 候选 / refined 层 1-2 候选**，边际收益递减（p=0.3 时 2→3 提升 +15pp、3→5 仅 +18pp）参数化。
12. **向量检索 O(n²) 修复**：随共享内核落地（见 2.1），**119s → 17ms**。

### 4.3 其他视频能力
- **结构化输出**：shot（景别）/ camera（机位运镜）/ motion_intensity（1-10）/ scene_transition（转场）/ continuity_token（跨镜头一致性令牌）/ duration_hint（时长）——下游 Story2Video 可直接消费。
- **JSON 输出失败重试**：结构化输出解析失败时带"只输出严格 JSON"提示重试（≤max_retries），耗尽回退原文保真。
- **关键词维度注入**：156KB 视频关键词词典（镜头/运镜/光影/色彩/风格/场景/动作），命中源提示词自动注入维度建议。
- **输入分类**：题材/镜头意图检测（classify + suggest_dimensions）。
- **语言路由**：按目标平台路由输出语言——**veo 英文优先 / doubao 中文优先**，策略约束对齐。
- **镜头纪律（lens discipline）**：character lock（主角锁定，逐字复用描述符）、STRICT 正反约束分块、final frame 终态、plausible negative（只列可能失败）。
- **文化锚定**：ethnicity anchoring 文化/族群锚定约束。
- **零文字伪影**：Zero Text Artifacts 强制约束（视频画面禁止多余文字/字幕/水印）。
- **批量优化**：≤20 条/批、有界并发 8、返回顺序一致。
- **双级缓存 + 统计**：`/v1/video/cache/stats` 可观测命中率。

### 4.4 API 端点
`POST /v1/video/optimize`、`POST /v1/video/optimize/batch`、`GET /v1/video/platforms`、`GET /v1/video/keywords`、`POST /v1/video/classify`、`POST /v1/video/feedback`、`GET /v1/video/cache/stats`、`GET /health`

---

## 五、桌面端契约层（Multi-Publish）

1. **字段收敛**：`excluded_characters` / `no_swap_pairs` / `color_ratio` 请求侧收敛（字符串与数组形态兼容、非法丢弃而非抛错、超限截断）+ **fail-closed 校验**（声明非空时必须真声明）。
2. **appendVideoTrailer 纯函数**：NON-IP/画幅/时长/音频收尾行模板，幂等追加、超长时保留 NON-IP 优先。
3. **平台参数画像**：`PLATFORM_VIDEO_PROFILES`——seedance 默认 15s / 1080p / 21:9 / audio on 等矩阵。
4. **精修层 max_length 层级**：按后端能力门控（8013 `[50,2000]` / 8020 `[200,20000]`），精修默认 5000 / 上限 20000。
5. **镜头纪律契约**：契约测试 **93/93**、关联套件 **240/240**（0 Critical）。

---

## 六、对用户的实际帮助（场景 × 收益）

| 使用场景 | 引擎能力 | 用户收益 |
|---|---|---|
| 新手一句话生成 | 模板直出 + 风格分类 + RAG few-shot | 无需懂平台语法，低创意等级下秒出可用提示词 |
| 多平台发布 | 7+6 平台策略 | 同一创意自动适配 MJ/SD/DALL·E/即梦/可灵/Veo/豆包…各平台最佳写法 |
| 批量生产 | 批量 API + 双级缓存 + 模板直出 | 重复请求零 LLM 成本，批量 20 条并发稳定 |
| 视频抽卡 | 成本模型（batch 3-5 / refined 1-2）+ 择优 | 用最少的钱拿到"至少一个可用"，避免 63 个候选烧 token |
| 角色一致性 | context 注入 + 角色卡 + continuity token + 缺席角色约束 | 长故事/系列镜头角色不漂移，缺席角色不会乱入 |
| 视频质量 | 镜头纪律 + 违规扣分 + 结构化输出 + 失败模式预防 | 废片率下降：文字伪影、角色漂移、光影跳变被事前拦截 |
| 导演级质感 | 17 位导演风格词典 | 输入风格名即获得对应视觉语言参考 |
| 语言适配 | veo 英文 / doubao 中文路由 | 平台母语输出，生成质量上限更高 |
| 成本与预算 | 预算硬化 + 缓存 + 截断保护 | 提示词长度、few-shot 注入、token 消耗全部可控 |
| 越用越好 | 反馈闭环（feedback + failure_stats） | 用户反馈沉淀进种子库，引擎持续进化 |
| 结果可信 | 对比评估 + 择优 + 缓存统计 | 每次优化可解释、可对比、可复现 |

---

## 七、测试与性能基线

- **全量测试**：654 passed / 3 skipped（P2 合并时实测记录）；Higgsfield 专项 89 项；共享内核锚定 11 项。
- **契约层**：`video-prompt-engine-contract.test.js` 93/93，关联套件 240/240。
- **性能**：向量检索 119s → 17ms（300 次 fuzz 逐位一致）；语料加载 3MB lru_cache 共享。
- **评审**：P0/P1/P2 均完成双模型评审（antigravity 不可用期间 Claude 降级），Critical 0 项。

---

## 八、演进路线（规划中，未实现）

- **image-engine-higgsfield-alignment**（OpenSpec change 已提案、规划产物就绪）：把视频侧 `select_best` / 违规扣分 / tier 层级同步到图片引擎（启发式评分 + excluded/swap 扣分 + 图片适配波段），提案见 `openspec/changes/image-engine-higgsfield-alignment/`。
- 图片/视频评估逻辑未来可进一步收敛到共享内核（当前语义对齐、双份存在）。

*报告完。本文档描述的能力均已在 `origin/main @ 85ff485`（prompt-engine）与 `main @ 87e25fd9`（Multi-Publish）上可验证。*
