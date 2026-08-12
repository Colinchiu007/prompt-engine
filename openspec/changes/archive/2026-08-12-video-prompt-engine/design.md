# Design — 独立视频提示词优化引擎

## Context

图片引擎架构（已调研，作为机制模板）：Optimizer 编排（CacheManager 双级缓存 → 低创意模板直出 → StyleCategoryClassifier 风格检测 → get_strategy 策略注册表 → PromptBuilder.build_system_prompt → context 注入 → RAGRetriever few-shot → LLMCaller 多候选 → post_process 结构化后处理 → 缓存写入）；策略 `@register` 自动注册；知识库 `seed_prompts.json → build.py → PromptVectorStore(TF-IDF)`；LLM 供应商 base/deepseek/gemini/minimax/openai_compat/xfyun。

目标：复刻该机制为**独立视频引擎**，运行时与图片引擎零耦合。

## Goals / Non-Goals

**Goals**
- 独立包 `video_prompt_engine/`：不 import `prompt_engine.*` 的 models/strategies/knowledge/cache/config。
- 独立服务 8020（图片 8013 不动）；独立知识库 `video_prompts_db`（视频种子，不加载图片 seed）。
- 视频关键词库：复用 7 个开源仓库构建（关键词词典 + few-shot 种子 + 平台策略指令）。
- 结构化视频输出（shot/camera/motion_intensity/scene_transition/continuity_token/duration_hint）+ Fact-Fidelity 保真。
- 批量契约：单批 ≤20、有界并发 8、结果顺序一致、逐条非空 fail closed。

**Non-Goals**
- 不迁移既有 `prompt_engine` 的 domain=video 分支（保留兼容，独立引擎为正式落点，文档标注）。
- 不做 Multi-Publish videogen 强制切换（8020 切换列为可选后续迁移）。
- 不引入外部向量库依赖（TF-IDF 自实现，与图片引擎一致）。

## Decisions

### D1: 独立包结构（镜像图片引擎机制，但不复用其代码）

```
video_prompt_engine/
  models.py            # 视频领域模型（自包含：VideoPlatformType/OptimizeRequest/…）
  config.py            # 独立配置（config_video.yaml；port 8020、knowledge.persist_dir=video_prompts_db）
  strategies/          # 视频平台策略注册表（@register；veo/kling/seedance/hailuo/doubao/generic_video）
  optimizer.py         # 编排（缓存→策略→system prompt→RAG few-shot→LLM→结构化后处理）
  prompt_builder.py    # system prompt + context 注入
  rag_retriever.py     # 视频知识库检索（platform 过滤）
  knowledge/           # seed_video_prompts.json + keywords_video.json + build.py + vector_store.py
  llm/                 # 供应商（base/minimax/openai_compat/gemini…，复用 config 的 provider 机制）
  api/rest.py          # FastAPI（/v1/video/*，端口 8020）
  cli.py               # python -m video_prompt_engine 入口
```
不 import `prompt_engine.*`（含 `02-source` 镜像）。

### D2: 视频知识库（7 仓库 → 三类资产）

| 来源 | 资产 | 用途 |
|---|---|---|
| img-prompt（5040 标签） | `keywords_video.json`：按视频维度抽关键词（动作 618/摄影 215/光影 144/色彩 228/艺术风格 136/素材 323/图像种类 204 等 → 映射为 镜头/运镜/光影/色彩/风格/场景/动作 词典，含中英） | 关键词维度词典（输入增强 + 分类） |
| awesome-video-prompts（50 结构化 JSON） | `seed_video_prompts.json`（few-shot 种子：shot/subject/scene 结构化视频提示词，标注平台/风格/分类） | RAG few-shot 高质量示例 |
| seedance2-skill | 策略指令模板（@引用语法、多模态输入、运镜复刻、特效模仿） | generic_video/seedance 策略 system prompt 素材 |
| awesome-seedance / awesome-seedance-2-prompts | 商用用例提示词（广告/电商/短剧） | few-shot 种子补充 |
| drama-skills | 短剧分镜/视频提示词工作流 | 策略模板（分镜/镜头/节奏） |
| stable-diffusion-videos | 动画技术（帧插值等） | 参考（不入库） |

### D3: 独立服务与批量契约

- `uvicorn video_prompt_engine.api.rest:app --port 8020`
- `POST /v1/video/optimize`（单条）、`POST /v1/video/optimize/batch`（≤20、Semaphore(8)）、`GET /v1/video/platforms`、`GET /v1/video/keywords`（关键词词典，供 UI/分类）、`GET /health`
- 请求/响应契约：`domain=video` 恒定；platform 枚举视频平台；creative_level 1-10；max_length 50-2000；context 白名单（synopsis/character/setting/character_list/full_text）+ 敏感键拦截；输出 `optimized_prompt` + 结构化 `video` 字段；fail closed（error→detail→空串）。

### D4: 策略体系（视频平台注册表）

- `BaseVideoStrategy`（复刻 BaseStrategy 机制）：build_system_prompt / post_process_video / extract_video_meta / render
- 首期策略：`generic_video`（六要素 + Fact-Fidelity + 镜头语言）、`seedance`（@引用语法 + 多模态约束，来自 seedance2-skill）、`veo`/`kling`/`hailuo`/`doubao`（平台差异参数占位，复用 generic 指令 + 平台特定约束）
- 未知平台回退 generic_video

### D5: 关键词库 → 优化增强

- 输入增强：命中 `keywords_video.json` 的关键词（运镜/光影/风格等）注入 system prompt 提示 LLM 使用视频语言
- 分类：`/v1/video/keywords` 供 UI 展示；可选关键词建议（借鉴 img-prompt 标签体系）


### D2.1 图片-视频知识共用性分析（决策依据）

**是否共享图片知识库（prompts_db）？不共享；但提炼共性视觉语言。**

| 维度 | 图片知识 | 视频知识 | 可否参考 |
|---|---|---|---|
| 视觉语言（光影/色彩/构图/风格/场景/材质） | 有 | 有（共通） | ✅ 提炼为关键词维度 |
| 运动/时间维度（motion/camera/transition/duration） | 无 | 有（视频独有） | ❌ 图片无此维度 |
| 结构化字段（shot/motion_intensity/continuity_token） | 无 | 有 | ❌ 图片种子缺这些字段 |
| 平台约束（运镜复刻/多模态/时长） | 风格参数 | 运镜/多模态/时长 | 各平台独立 |

结论：
- **直接共享图片种子作为视频 few-shot 有害**：静态画面描述缺运动/镜头/时间维度，会诱导视频模型输出静止画面式提示词（漏 camera/motion），降低视频质量。
- **图片知识的正确复用方式 = 提炼视觉维度关键词**（keywords_video.json：scene/action/camera/lighting/color/material/style，源自 img-prompt 标签体系），注入 system prompt 作为视觉语言提示；**few-shot 层只用视频专属种子**（awesome-video-prompts 结构化视频提示词）。

## Risks / Trade-offs

- [独立包导致代码重复（与图片引擎机制相似）] → 有意为之（用户要求完全分离）；共享仅限文档级"机制模板"，代码零耦合
- [7 仓库数据规模大（img-prompt 5040）] → 仅提取视频维度子集入词典；种子库精选（awesome-video-prompts 50 + 商用用例）
- [许可问题] → img-prompt MIT、awesome-video-prompts 无明确许可（README 精选）→ 种子标注来源，仅内部使用
- [既有 domain=video 分支并存] → 独立引擎为正式落点，旧分支保留兼容；文档标注迁移路径

## Migration Plan

- 独立服务先并行运行（8020）；验证通过后文档标注正式落点；Multi-Publish videogen 切换列为后续任务
- 回滚：新服务独立，删除/停用不影响图片引擎

## Open Questions

无（分离粒度、知识库范围、端口已在 D1-D5 定案）。
