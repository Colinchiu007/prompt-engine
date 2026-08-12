# ARCH — 独立视频提示词优化引擎架构设计

> 版本：v1.0 ｜ 日期：2026-08-12 ｜ 关联 OpenSpec change：`video-prompt-engine`
> 关联 PRD：`01-docs/PRD-video-prompt-engine.md`

## 1. 架构总览

```
输入（视频提示词 / 批量 / 平台 / context）
   │
   ▼
[video_prompt_engine.api.rest] 端口 8020
   │  POST /v1/video/optimize / optimize/batch / platforms / keywords / health
   ▼
[VideoOptimizer] 编排
   ├─ 内存缓存（同请求命中）
   ├─ 策略注册表 get_strategy(platform) → generic_video / seedance（未知回退 generic_video）
   ├─ VideoPromptBuilder.build_system_prompt（六要素 + Fact-Fidelity + 关键词维度提示）
   ├─ build_context_section（白名单 context 注入）
   ├─ VideoRAGRetriever.retrieve_few_shot（video_prompts_db，platform 过滤）
   ├─ BaseVideoLLMProvider.call（LLM 调用）
   └─ post_process_video（结构化：shot/camera/motion/transition/continuity/duration）
   │
   ▼
输出：optimized_prompt + video 结构化字段（fail closed）
```

**与图片引擎完全分离**：不 import `prompt_engine.*`；独立端口/知识库/策略/模型/缓存/配置。

## 2. 模块设计

| 模块 | 职责 | 关键实现 |
|---|---|---|
| `models.py` | 视频领域模型 + context 白名单 + 敏感键拦截 | VideoPlatformType（10 平台 + 别名）、VideoOptimizeRequest/Result、VideoPromptMeta、VideoBatchOptimizeRequest（≤20） |
| `config.py` | config_video.yaml + VIDEO_* 环境变量 | port 8020、knowledge.persist_dir=video_prompts_db、llm provider |
| `strategies/` | 视频平台策略注册表 | base.py（@register/get_strategy/post_process_video）、generic_video.py（六要素+Fact-Fidelity）、seedance.py（@引用/多模态） |
| `knowledge/` | 视频关键词 + few-shot 种子 + TF-IDF | keywords_video.json（7 维度 2059 条）、seed_video_prompts.json（11 结构化）、build.py、vector_store.py |
| `rag_retriever.py` | 视频 few-shot 检索 | platform 过滤 + top_k |
| `llm/` | 供应商 | BaseVideoLLMProvider（openai_compat/minimax/gemini 语义） |
| `optimizer.py` | 编排 | 缓存→策略→prompt→context→RAG→LLM→结构化后处理；optimize_batch 线程池并发 8 |
| `api/rest.py` | REST | /health、/v1/video/* 端点 |

## 3. 数据契约

### 3.1 请求（/v1/video/optimize）
```json
{
  "prompt": "关羽率军北伐，秋雨连绵，水淹七军",
  "platform": "seedance",
  "style": null,
  "creative_level": 5,
  "max_length": 500,
  "num_candidates": 1,
  "negative_prompt": "现代元素, 文字",
  "context": { "synopsis": "襄樊之战", "character": "关羽", "character_list": ["关羽","曹操"], "setting": "东汉末年", "full_text": "..." }
}
```
校验：prompt 非空 ≤2000；platform 别名归一/未知回退；creative_level 1-10；max_length 50-2000；context 白名单 + 敏感键拦截。

### 3.2 响应
```json
{
  "optimized_prompt": "Cinematic wide shot of General Guan Yu...",
  "platform": "seedance",
  "model_used": "MiniMax-M2.7",
  "video": { "shot": "wide", "camera": "dolly", "motion_intensity": 7, "scene_transition": "cut", "continuity_token": "guanyu_xiangfan", "duration_hint": 5 }
}
```
fail closed：error → 502 detail；optimized_prompt 空 → 回退原文（结构化字段置空）。

### 3.3 批量（/v1/video/optimize/batch）
- 单批 ≤20（422 拒绝）；线程池并发 8；结果顺序与请求一致；逐条非空。

## 4. 视频知识库（7 仓库 → 两类资产）

| 资产 | 来源 | 内容 | 用途 |
|---|---|---|---|
| keywords_video.json | img-prompt（5040 标签） | 7 维度 2059 条中英关键词（scene 395/action 618/camera 215/lighting 144/color 228/material 323/style 136） | 输入增强（命中注入 system prompt）+ GET /v1/video/keywords |
| seed_video_prompts.json | awesome-video-prompts（50 案例） | 11 个结构化 JSON 视频提示词 | RAG few-shot 种子（platform 过滤） |
| seedance 策略指令 | seedance2-skill | @引用语法、多模态约束、运镜复刻 | strategies/seedance.py system prompt |
| 商用用例补充 | awesome-seedance / -2 | 广告/电商/短剧提示词 | 后续种子扩充 |
| 分镜模板 | drama-skills | 短剧分镜/视频提示词工作流 | 后续策略模板 |
| 动画技术参考 | stable-diffusion-videos | 帧插值等 | 参考（不入库） |

**共用性原则**：few-shot 只使用视频专属种子；图片知识的视觉维度（光影/色彩/风格/场景）以关键词形式提炼注入（不共享图片种子库）。

## 5. 错误码与提示文字

| 错误码/场景 | 语义 | 提示文字 |
|---|---|---|
| LLM API Key 未配置 | 502 detail | "视频引擎 LLM API Key 未配置（VIDEO_LLM_API_KEY）" |
| 批量 >20 | 422 | "优化请求列表，最多 20 条" |
| 敏感键 | 400/422 | "context.xxx 包含敏感凭据键，已拒绝外发" |
| 优化失败 | 502 | "video optimize failed: {detail}" |

## 6. 部署

- `python -m video_prompt_engine.cli --build-kb`（构建视频知识库）
- `python -m video_prompt_engine`（uvicorn 8020，config_video.yaml / VIDEO_LLM_* 环境变量）
- 与图片引擎 8013 并行运行；回滚 = 停 8020 服务（不影响图片引擎）

## 7. 测试策略

| 模块 | 用例 |
|---|---|
| models | 平台别名/未知回退、批量 ≤20、敏感键拦截、context 白名单 |
| strategies | 注册表、generic_video Fact-Fidelity、seedance 多模态、结构化后处理、未知平台回退 |
| knowledge | 关键词加载、种子加载、关键词提示命中 |
| optimizer | 结构化输出、空输出回退、缺 key fail closed、批量顺序非空 |
| api | health/platforms/keywords、12 条单批 |
| independence | 源码无 import prompt_engine |
| 回归 | 图片引擎 tests（test_video_optimize + test_batch）全绿 |

## 8. 版本历史
- v1.0（2026-08-12）：独立引擎 + 视频知识库 + 分离边界。
