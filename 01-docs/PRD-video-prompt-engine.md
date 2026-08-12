# PRD — 独立视频提示词优化引擎（video-prompt-engine）

> 版本：v2.0 ｜ 日期：2026-08-12 ｜ 状态：待评审
> 关联 OpenSpec change：`video-prompt-engine` / `video-prompt-engine-enhancement`
> 仓库：prompt-engine（`video_prompt_engine/` 独立包，端口 8020）

## 1. 背景与目标

### 1.1 背景
- 图片 prompt-engine（`prompt_engine/`，8013）是图片提示词优化引擎。此前 video 领域被加为其 `domain=video` 分支（同一服务、共享知识库/缓存/框架）。
- **用户明确要求：视频提示词优化引擎与图片引擎分开，不要混在一起。** v1.0 已完成独立包 + 独立端口（8020），源码零 import 图片引擎。
- **v2.0（本版）** 补齐机制差距：知识库扩充（11→140 种子）、SQLite 双级缓存、JSON 结构化输出重试、多平台专项策略（veo/kling/hailuo/doubao）、输入分类（题材/镜头意图）、评估与反馈闭环、中文输出、Multi-Publish videogen 集成切换（8020 优先 + 8013 回退）。

### 1.2 目标（v2.0）
- **P0 知识库扩充**：种子 140 条（awesome-video-prompts 105 + seedance2-skill 28 + awesome-seedance 7），按平台分层；向量检索 miss 时关键词命中兜底。
- **P0 结构化输出重试**：JSON 解析失败带「只输出严格 JSON」提示重试 ≤2 次，耗尽回退原文并标记 `retried`。
- **P0 多平台专项策略**：veo（长镜头/真实感）、kling（运动物理/细节）、hailuo（节奏/剪辑）、doubao（中文优先）；未知平台回退 generic_video。
- **P0 SQLite 双级缓存**：内存 + SQLite 持久，key=platform|prompt|creative_level|max_length|language|num_candidates|negative_prompt|context_hash；命中跳过 LLM。
- **P1 输入分类**：题材（历史/科幻/广告/短剧/自然/人物/电影感）+ 镜头意图（动态/静态/全景/特写）→ 注入 system prompt + 关键词维度建议。
- **P1 评估与反馈闭环**：evaluator（保真/六要素/镜头字段/长度 → 0-100 分）多候选择优；feedback 好评沉淀种子库 / 坏评降质量分。
- **P1 中文输出**：`output_language=zh`（默认 en）；zh 保留中文主体 + 镜头术语双语，结构化枚举仍英文。
- **P2 videogen 集成**：Multi-Publish `VIDEO_PROMPT_PORT=8020` 启用独立引擎优先，失败/未配置回退 8013 `domain=video`（兼容）。

### 1.3 非目标
- 不迁移既有 `prompt_engine` 的 domain=video 分支（保留兼容；独立引擎为视频优化正式落点）。
- 不引入外部向量库依赖（TF-IDF 自实现）与 Redis（SQLite 已满足单机持久）。
- 平台策略差异基于公开资料（标注「首版近似」），平台实测后续校准。

## 2. 与图片引擎的分离边界

| 维度 | 图片引擎 prompt_engine（8013） | 视频引擎 video_prompt_engine（8020） |
|---|---|---|
| Python 包 | `prompt_engine/` | `video_prompt_engine/`（静态断言无 `import prompt_engine`） |
| REST 端口 | 8013 | 8020 |
| 知识库 | prompts_db（图片种子） | video_prompts_db（视频种子 140 条） |
| 缓存 | 图片 CacheManager | 独立 VideoCacheManager（video_prompt_cache.db） |
| 策略 | midjourney/sd/dalle/... | generic_video/seedance/veo/kling/hailuo/doubao |
| 模型/配置 | config.yaml | config_video.yaml + VIDEO_* 环境变量 |
| 命名 | prompt-engine-contract.js（图片） | video-prompt-engine-contract.js（视频，刻意分文件） |
## 3. 功能逻辑

### 3.1 优化主流程（VideoOptimizer）
```
请求 → 敏感 context 键拦截 → 语言归一（output_language）→ 缓存 key 计算
  → 双级缓存命中? → 返回（cache_hit=true，跳过 LLM）
  → 策略加载（get_strategy(platform)，未知回退 generic_video）
  → 输入分类（classify → 题材/镜头意图 + 建议关键词维度）
  → system prompt = 策略.build_system_prompt(style/creative/max_length/negative/keywords_hint/output_language)
                   + 分类段 + context 段 + RAG few-shot（向量 → 关键词兜底）
  → 循环 num_candidates 次：
      LLM 调用 → <think> 推理块剥离 → JSON 解析失败? → 带 JSON_RETRY_HINT 重试（≤max_retries=2）
      → post_process_video（渲染单串 + video 字段）→ 超长截断 → 空串回退原文
  → num_candidates>1：evaluator 评分择优（最优在前，candidates 按分降序）
  → fail-closed 校验 → 缓存写入 → 返回
```

### 3.2 批量优化（Batch）
- `POST /v1/video/optimize/batch`：单批 ≤20（pydantic `min_length=1, max_length=20`）；`ThreadPoolExecutor(max_workers=8)` 有界并发；`pool.map` 保持结果顺序与请求一致；逐条 fail closed（error 优先 → 空串拒绝）。
- 12 条单批 200（对齐 videogen 12 场景单批）；>20 由调用方分块兜底。

### 3.3 知识库与检索
- **种子 140 条**：generic_video 105（awesome-video-prompts）+ seedance 35（seedance2-skill 28 + awesome-seedance 7）；字段含 id/title/description/prompt_text/language/platform/style/categories/quality_score/source。
- **向量检索**：TF-IDF 余弦相似 + platform 过滤（命中平台或 generic_video 种子），top_k=3（可配）。
- **关键词兜底**：向量无命中时按输入分词（中文 2-6 字片段 + 英文词）命中种子 title/description/document/categories，平台精确优先，返回 top_k。
- **关键词词典**：`keywords_video.json` 7 维度（scene/action/camera/lighting/color/material/style）中英关键词；输入命中 → `## 视频关键词参考` 段注入。

### 3.4 策略体系（6 个已注册）
| 策略 | 平台 | 特性（首版近似） |
|---|---|---|
| generic_video | 通用 | 六要素 + Fact-Fidelity + 150-300 词详细要求 |
| seedance | 即梦 | @引用语法 / 多模态输入约束 / 运镜复刻 |
| veo | Veo | 长镜头连续、真实物理、自然运镜 |
| kling | 可灵 | 运动物理、动态细节（织物/毛发/水/粒子） |
| hailuo | 海螺 | 节奏/剪辑/氛围、转场意图 |
| doubao | 豆包 | 中文优先理解、主体-动作-环境结构 |

- 所有策略支持 `output_language`：zh 时注入「Output Language (MANDATORY)」中文主体 + 镜头术语双语指令；`shot/camera/scene_transition` 枚举保持英文。
- 输出结构化：`{prompt, shot, camera, motion_intensity, scene_transition, continuity_token, duration_hint}`。

### 3.5 缓存（双级）
- `VideoCacheManager`：L1 内存 dict（容量 512，超限截断）+ L2 SQLite `video_prompt_cache.db`（`INSERT OR REPLACE`，key 主键）。
- key：`platform|language|sha1(prompt)|sha1(style)|creative_level|max_length|num_candidates|sha1(negative_prompt)|context_sha1[:16]`（组件哈希防 `|` 碰撞；style 纳入避免跨风格误命中）。
- 命中：直接返回缓存结果（`cache_hit=true`），不调 LLM；`GET /v1/video/cache/stats` 返回内存/容量/SQLite 计数。
- 配置：`cache.enabled`（默认 true）、`cache.dir`（默认 video_prompt_cache，`VIDEO_CACHE_DIR` 可覆盖）、`cache.memory_size`。

### 3.6 输入分类
- `classifier.py`：题材 8 类（history/scifi/ad/drama/nature/portrait/cinematic/general）+ 镜头意图 4 类（dynamic/static/wide/closeup）关键词检测。
- `suggest_dimensions`：题材 → 关键词维度建议（如 history→scene/style/camera/lighting）。
- 注入：`## 输入题材/镜头意图检测（仅供参考，不得改变事实）` + 题材/镜头意图/建议维度；**不改变事实**（Fact-Fidelity 优先）。

### 3.7 评估与反馈
- `evaluator.py`：score = 长度(20) + 六要素(30) + shot(20) + camera(15) + motion(15) + 保真(20)，0-100；zh 长度按字符（120-4000），en 按词（100-400）。
- 多候选择优：`select_best` 返回最高分候选；`candidates` 按分降序。
- `feedback.py`：`POST /v1/video/feedback`，prompt_text/result_prompt 空值 422；好评 → 结果提示词入反馈种子文件（quality_score=9，id 时间戳防撞）；坏评 → 匹配源提示词质量分 -1（最低 1）。**落盘路径为可写数据目录**（默认 `video_prompt_cache/feedback_seed.json`，`VIDEO_FEEDBACK_PATH` 覆盖），避免写入 wheel 包内只读的 `knowledge/seed_video_prompts.json`；进程内锁 + 原子写（临时文件 + replace）防并发丢失更新。

### 3.8 中文输出
- 请求 `output_language`：en（默认）/zh；`pattern="^(zh|en)$"`，非法 422。
- zh：`prompt` 字段中文详细描写（等价 150-300 英文词的丰富度），镜头术语双语（如 中景 medium shot、推镜 dolly-in、金色时刻 golden hour）；`shot/camera/scene_transition` 保持英文枚举。
- 响应 `language` 反映实际输出语言；缓存 key 含 language 隔离。

### 3.9 videogen 集成（Multi-Publish）
- `video-prompt-engine-contract.js`：新增 `buildStandaloneVideoOptimizeRequest`（8020 请求，无 domain、含 output_language）、`isStandaloneVideoEngineEnabled`（`VIDEO_PROMPT_PORT` 合法端口）、`getStandaloneVideoEngineTarget`（host 默认 127.0.0.1）。
- `prompt-bridge.js`：`optimizeVideo`/`optimizeVideosBatch` 独立引擎（8020 `/v1/video/optimize[/batch]`）优先；连接失败/超时 → warning + 回退 8013 `/v1/optimize[/batch]`（domain=video）。
- `output_language` 自动检测：文本 CJK 字符占比 ≥30% → zh，否则 en；显式 `output_language`/`outputLanguage` 优先。
- 独立引擎需单独启动（`python -m video_prompt_engine`，8020）；未配置 `VIDEO_PROMPT_PORT` 时零回归走 8013。
## 4. 数据校验

### 4.1 请求（/v1/video/optimize）
| 字段 | 校验 | 越界/非法 |
|---|---|---|
| prompt | 非空，≤2000（pydantic min_length=1, max_length=2000） | 空 → 422 |
| platform | 视频平台枚举/别名 | 未知 → 回退 generic_video（不 422） |
| style | ≤50 | 越界 422 |
| creative_level | 1-10 | 越界 422 |
| max_length | 200-4000（默认 1800） | 越界 422 |
| num_candidates | 1-5 | 越界 422 |
| negative_prompt | ≤500 | 越界 422 |
| context | 白名单键（synopsis/character/setting/character_list/full_text/narrative_intent/scene_type） | 未知键忽略 + warning；敏感键（api_key/token/secret/password/authorization）递归拦截 → 抛错 |
| output_language | en/zh | 非法 422 |

### 4.2 响应 fail closed
- `error` 非空 → HTTP 502；`detail` 非空 → 422 语义；`optimized_prompt` 必须非空字符串。
- 结构化失败重试耗尽 → 回退原文（`optimized_prompt=原文`，`retried=次数`）。
- 视频字段越界收敛（motion_intensity 1-10）、缺失给默认（motion=5）；`prompt` 超 max_length 截断。

### 4.3 配置（config_video.yaml）
| 键 | 默认 | 说明 |
|---|---|---|
| server.port | 8020 | 独立端口（VIDEO_ENGINE_PORT 覆盖） |
| knowledge.enabled/persist_dir | true / video_prompts_db | 向量库 |
| knowledge.retrieval.top_k | 3 | few-shot 数量 |
| llm.provider/model/api_key/base_url/timeout | openai_compat / 空 / 60 | VIDEO_LLM_* 环境变量覆盖 |
| optimizer.cache_size / max_retries | 512 / 2 | 内存缓存容量 / JSON 重试次数 |
| cache.enabled / dir / memory_size | true / video_prompt_cache / 512 | VIDEO_CACHE_DIR / VIDEO_CACHE_DISABLED 覆盖 |

## 5. 交互逻辑与显示项

### 5.1 API 端点一览（8020）
| 端点 | 方法 | 说明 |
|---|---|---|
| /health | GET | 健康检查（version=0.2.0） |
| /v1/video/optimize | POST | 单条优化（含 output_language/num_candidates/context） |
| /v1/video/optimize/batch | POST | 批量 ≤20，并发 8，顺序一致 |
| /v1/video/platforms | GET | 已注册平台策略枚举（非全量枚举） |
| /v1/video/keywords | GET | 关键词词典（按维度，前 50/维度） |
| /v1/video/classify | POST | 输入题材/镜头意图检测 |
| /v1/video/feedback | POST | 好/坏反馈闭环 |
| /v1/video/cache/stats | GET | 双级缓存统计 |

### 5.2 调用方交互（videogen）
- 配置 `VIDEO_PROMPT_PORT=8020` 启用独立引擎；独立引擎不可用 → 日志 warning + 自动回退 8013（业务方无感，结果契约一致）。
- `output_language` 自动检测：中文文案自动 zh（保留中文主体 + 英文镜头术语），英文文案 en。
- 响应增强字段：`language`（实际语言）、`cache_hit`（是否缓存）、`retried`（重试次数）、`classification`（题材/镜头意图），供调用方展示与诊断。

### 5.3 显示项（前端预留）
- `GET /v1/video/keywords`：按维度展示「视频关键词建议」（中英双语 + 维度标签）。
- 分类结果展示：`题材：历史｜镜头意图：动态`（来自 `classification`）。
- 提示文字示例：
  - 优化成功：`视频提示词已优化（镜头：中景｜运镜：推镜｜光影：金色时刻｜语言：中文）`
  - 缓存命中：`已命中缓存（相同请求），未重复调用模型`
  - JSON 重试：`结构化输出解析失败，已自动重试 N 次`
  - 回退 8013：`独立视频引擎不可用，已回退兼容引擎（domain=video）`
  - 反馈提交：`感谢反馈：好评已沉淀入知识库 / 该提示词质量分已下调`

## 6. 验收标准

| # | 验收项 | 判定 |
|---|---|---|
| A1 | 独立服务 8020 /health | ok；8013 不受影响 |
| A2 | 源码无 import prompt_engine | 静态断言通过 |
| A3 | 知识库 ≥100 种子、平台分层 | 140 条（generic 105 + seedance 35） |
| A4 | 双级缓存命中 | 同请求二次 cache_hit=true、LLM 不重复调用、SQLite 跨实例命中 |
| A5 | JSON 重试 | 失败带提示重试 ≤2，耗尽回退原文 + retried 标记 |
| A6 | 平台策略 | veo/kling/hailuo/doubao 注册 + 平台约束 + 语言段 |
| A7 | 输入分类 | 历史/科幻等题材检测 + 维度建议注入 |
| A8 | 多候选择优 | num_candidates>1 时最优在前 |
| A9 | 反馈闭环 | 好评入种子 / 坏评降分 / 空值 422 |
| A10 | 中文输出 | output_language=zh → language=zh、中文详细提示词、枚举英文 |
| A11 | videogen 集成 | VIDEO_PROMPT_PORT=8020 优先；不可用回退 8013 记录 warning |
| A12 | 真实 LLM E2E | 中文长文案 → 详细中文提示词（≥200 字）无 think 块、批量 12 全过、缓存命中 |
| A13 | 图片引擎回归 | 既有测试全绿（Windows 本地已知 GBK 读取问题除外，CI Ubuntu 全绿） |

## 7. 版本历史
- v1.0（2026-08-12）：初版（独立引擎 + 视频关键词库 + 分离边界）。
- v2.0（2026-08-12）：全面增强（140 种子/双级缓存/JSON 重试/四平台策略/输入分类/评估反馈/中文输出/videogen 集成）。
