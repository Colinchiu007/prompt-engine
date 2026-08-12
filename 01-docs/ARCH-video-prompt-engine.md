# ARCH — 独立视频提示词优化引擎架构设计

> 版本：v2.0 ｜ 日期：2026-08-12 ｜ 关联 OpenSpec change：`video-prompt-engine` / `video-prompt-engine-enhancement`
> 关联 PRD：`01-docs/PRD-video-prompt-engine.md`

## 1. 架构总览

```
输入（视频提示词 / 批量 / 平台 / context / output_language）
   │
   ▼
[video_prompt_engine.api.rest] 端口 8020
   │  /health /v1/video/optimize /optimize/batch /platforms /keywords /classify /feedback /cache/stats
   ▼
[VideoOptimizer] 编排
   ├─ 敏感 context 键拦截 → 语言归一（zh/en）→ 缓存 key（platform|prompt|creative|max_length|lang|num|negative|ctx_hash）
   ├─ VideoCacheManager（L1 内存 dict + L2 SQLite video_prompt_cache.db）→ 命中即返（cache_hit=true）
   ├─ 策略注册表 get_strategy(platform) → generic_video/seedance/veo/kling/hailuo/doubao（未知回退 generic_video）
   ├─ classifier.classify（题材/镜头意图）→ 分类段注入 + suggest_dimensions 维度建议
   ├─ VideoPromptBuilder.build_system_prompt（六要素 + Fact-Fidelity + 关键词维度提示 + output_language 语言段）
   ├─ build_context_section（白名单 context 注入）
   ├─ VideoRAGRetriever.retrieve_few_shot（video_prompts_db 向量 → 无命中关键词兜底平台种子）
   ├─ BaseVideoLLMProvider.call（LLM 调用，含 <think> 剥离）
   ├─ JSON 结构化重试（解析失败 → JSON_RETRY_HINT 重试 ≤2 → 耗尽回退原文 + retried 计数）
   ├─ evaluator.select_best（num_candidates>1 时评分择优，candidates 按分降序）
   └─ post_process_video（结构化：shot/camera/motion/transition/continuity/duration）
   │
   ▼
输出：optimized_prompt + video 结构化字段 + language/cache_hit/retried/classification（fail closed）
```

**与图片引擎完全分离**：不 import `prompt_engine.*`；独立端口/知识库/缓存/策略/模型/配置；Multi-Publish 侧契约文件刻意分文件命名。

## 2. 模块设计

| 模块 | 职责 | 关键实现 |
|---|---|---|
| `models.py` | 视频领域模型 + context 白名单 + 敏感键拦截 | VideoPlatformType（10 平台 + 别名）、VideoOptimizeRequest（含 output_language pattern zh/en）、VideoOptimizeResult（language/cache_hit/retried/classification）、VideoPromptMeta、VideoBatchOptimizeRequest（≤20）、VideoFeedbackRequest/VideoClassifyRequest |
| `config.py` | config_video.yaml + VIDEO_* 环境变量 | port 8020、knowledge.persist_dir、llm provider、optimizer.max_retries、cache.enabled/dir/memory_size（VIDEO_CACHE_DIR/VIDEO_CACHE_DISABLED 覆盖） |
| `cache_manager.py` | 双级缓存 | VideoCacheManager：内存 dict（容量截断）+ SQLite（INSERT OR REPLACE，key 主键）；stats() |
| `classifier.py` | 输入分类 | GENRE_KEYWORDS（8 题材）+ SHOT_INTENT（4 镜头意图）+ suggest_dimensions（题材→维度映射） |
| `evaluator.py` | 质量评估 | evaluate() 0-100（长度/六要素/镜头字段/保真）；select_best() 多候选择优 |
| `feedback.py` | 反馈闭环 | VideoFeedbackStore：好评结果入种子（score=9）/坏评降分；空值抛 ValueError |
| `strategies/` | 视频平台策略注册表 | base.py（@register/get_strategy/build_language_section）、generic_video.py（六要素+Fact-Fidelity+150-300词）、seedance.py（@引用/多模态）、veo/kling/hailuo/doubao（平台约束） |
| `knowledge/` | 视频关键词 + few-shot 种子 + TF-IDF | keywords_video.json（7 维度 2059 条）、seed_video_prompts.json（140 条：generic 105 + seedance 35）、build.py、vector_store.py |
| `rag_retriever.py` | 视频 few-shot 检索 | 向量（platform 过滤 + top_k）→ 无命中关键词兜底（平台种子 top_k） |
| `llm/` | 供应商 | BaseVideoLLMProvider（openai_compat/minimax/gemini 语义；无 key fail closed） |
| `optimizer.py` | 编排 | 缓存→分类→策略→prompt→RAG→LLM→重试→择优→后处理；optimize_batch 线程池并发 8 |
| `api/rest.py` | REST | /health、/v1/video/{optimize,optimize/batch,platforms,keywords,classify,feedback,cache/stats} |

## 3. 数据契约

### 3.1 请求（/v1/video/optimize）
```json
{
  "prompt": "关羽率军北伐，秋雨连绵，水淹七军",
  "platform": "seedance",
  "style": null,
  "creative_level": 5,
  "max_length": 1800,
  "num_candidates": 1,
  "negative_prompt": "现代元素, 文字",
  "context": { "synopsis": "襄樊之战", "character": "关羽", "setting": "东汉末年", "full_text": "..." },
  "output_language": "zh"
}
```
校验：prompt 非空 ≤2000；platform 别名归一/未知回退；creative_level 1-10；max_length 200-4000（默认 1800）；num_candidates 1-5；negative_prompt ≤500；context 白名单 + 敏感键拦截；output_language pattern zh/en（非法 422）。

### 3.2 响应
```json
{
  "optimized_prompt": "关羽策马立于曹军阵前，赤面长髯，面若重枣……夕阳西斜，金色余晖洒在铁甲之上",
  "platform": "generic_video",
  "model_used": "MiniMax-M2.7",
  "video": { "shot": "medium_wide", "camera": "pan", "motion_intensity": 7, "scene_transition": "cut", "continuity_token": "关羽-赤面长髯-青龙偃月刀-白马之战", "duration_hint": null },
  "language": "zh",
  "cache_hit": false,
  "retried": 0,
  "classification": { "genres": ["history"], "shot_intents": [], "primary_genre": "history" }
}
```
fail closed：error → 502；detail → 422 语义；optimized_prompt 空 → 回退原文；结构化字段越界收敛、缺失给默认。

### 3.3 批量（/v1/video/optimize/batch）
- 单批 ≤20（422 拒绝）；`ThreadPoolExecutor(8)` 并发；结果顺序与请求一致；逐条 fail closed。

### 3.4 缓存 key
`platform|prompt|creative_level|max_length|language|num_candidates|negative_prompt|context_sha1[:16]`（含语言隔离；SQLite 主键）。

### 3.5 反馈（/v1/video/feedback）
`{prompt_text, result_prompt, good, source}`：空值 422；好评 → 结果入反馈种子文件（quality_score=9，id=时间戳+序号防撞）；坏评 → 源提示词匹配种子质量分 -1（下限 1）。
落盘：可写数据目录（默认 `video_prompt_cache/feedback_seed.json`，`VIDEO_FEEDBACK_PATH` 覆盖）；进程内锁 + 原子写（tmp + os.replace）。
## 4. 视频知识库（7 仓库 → 两类资产）

| 资产 | 来源 | 内容 | 用途 |
|---|---|---|---|
| keywords_video.json | img-prompt（5040 标签） | 7 维度 2059 条中英关键词（scene/action/camera/lighting/color/material/style） | 输入增强（命中注入 system prompt）+ GET /v1/video/keywords |
| seed_video_prompts.json | awesome-video-prompts（105）+ seedance2-skill（28）+ awesome-seedance（7） | 140 个视频提示词种子（platform 分层：generic_video 105 + seedance 35；quality_score/source 标注） | RAG few-shot + 关键词兜底 |
| seedance 策略指令 | seedance2-skill | @引用语法、多模态约束、运镜复刻 | strategies/seedance.py system prompt |
| 商用用例补充 | awesome-seedance / -2 | 广告/电商/短剧提示词 | 种子库扩充 |
| 分镜模板 | drama-skills | 短剧分镜/视频提示词工作流 | 策略模板素材 |
| 动画技术参考 | stable-diffusion-videos | 帧插值等 | 参考（不入库） |

**共用性原则**：few-shot 只使用视频专属种子；图片知识的视觉维度（光影/色彩/风格/场景）以关键词形式提炼注入，**不共享图片种子库**（用户要求两者分开）。

## 5. 错误码与提示文字

| 错误码/场景 | 语义 | 提示文字 |
|---|---|---|
| LLM API Key 未配置 | 502 detail | "视频引擎 LLM API Key 未配置（VIDEO_LLM_API_KEY）" |
| 批量 >20 | 422 | "优化请求列表，最多 20 条" |
| 敏感键 | 400/422 | "context.xxx 包含敏感凭据键，已拒绝外发" |
| output_language 非法 | 422 | "String should match pattern '^(zh\|en)$'" |
| feedback 空值 | 422 | "prompt_text / result_prompt 不能为空" |
| JSON 重试 | 内部 | 第二次调用附加 JSON_RETRY_HINT（只输出严格 JSON） |
| videogen 回退 | warning 日志 | "独立视频引擎(host:port)不可用，回退 8013 domain=video：{原因}" |

## 6. 部署

- 构建视频知识库：`python -m video_prompt_engine.cli --build-kb`（生成 video_prompts_db/ 向量索引）
- 启动：`python -m video_prompt_engine`（uvicorn 8020；`VIDEO_LLM_PROVIDER/BASE_URL/MODEL/API_KEY` 环境变量；`VIDEO_CACHE_DIR` 可指定缓存目录）
- 与图片引擎 8013 并行运行；回滚 = 停 8020 服务（不影响图片引擎）
- Multi-Publish videogen：设置 `VIDEO_PROMPT_PORT=8020` 启用独立引擎优先；未设置/不可用自动回退 8013（`video-prompt-engine-contract.js` / `prompt-bridge.js`）

## 7. 测试策略

| 模块 | 用例 |
|---|---|
| models | 平台别名/未知回退、批量 ≤20、敏感键拦截、context 白名单、output_language 校验 |
| strategies | 注册表（含 veo/kling/hailuo/doubao）、平台约束、zh/en 语言段、结构化后处理、未知平台回退 |
| knowledge | 关键词加载、种子加载（140）、关键词提示命中 |
| cache | 命中跳过 LLM、key 含语言、SQLite 跨实例、禁用开关、stats |
| optimizer | JSON 重试（带提示/耗尽回退）、分类注入、多候选择优、zh 输出、批量顺序非空、缺 key fail closed |
| evaluator/feedback | 评分范围、select_best、空值校验、好评沉淀/坏评降分 |
| rag | 向量 miss → 关键词兜底平台种子 |
| api | health/platforms（已注册）/keywords/classify/feedback/cache/stats、12 条单批、zh 单条 |
| videogen 集成（Multi-Publish） | 独立引擎请求构造（无 domain/output_language 检测）、8020 优先、失败回退 8013、未启用零回归 |
| independence | 源码无 import prompt_engine |
| 回归 | 图片引擎 tests 全绿（Windows 本地 `test_resources_preview` 已知 GBK 读取问题除外；CI Ubuntu UTF-8 全绿） |

## 8. 版本历史
- v1.0（2026-08-12）：独立引擎 + 视频知识库 + 分离边界。
- v2.0（2026-08-12）：全面增强（140 种子/双级缓存/JSON 重试/四平台策略/输入分类/评估反馈/中文输出/videogen 集成）。
