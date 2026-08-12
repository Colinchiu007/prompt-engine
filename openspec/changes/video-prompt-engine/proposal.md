# video-prompt-engine — 独立视频提示词优化引擎（与图片引擎完全分离）

## Why

图片 prompt-engine（`prompt_engine/`，8013）目前把 video 领域作为同一服务内的 `domain=video` 分支：共享同一 API 端口、共享 RAG 知识库（图片种子 `seed_prompts.json`）、共享缓存/配置/`models.py`/`optimizer.py`。用户明确要求**视频提示词优化引擎与图片引擎分开，不要混在一起**。同时需要一个**视频专属关键词/提示词库**（复用 7 个开源仓库：rockbenben/img-prompt、songguoxs/awesome-video-prompts、dexhunter/seedance2-skill、ZeroLu/awesome-seedance、YouMind-OpenLab/awesome-seedance-2-prompts、worldwonderer/drama-skills、nateraw/stable-diffusion-videos）。

## What Changes

- **新建独立视频引擎包 `video_prompt_engine/`**：独立 REST 服务（新端口 8020）、独立模型/策略/知识库/缓存/配置；**不 import 图片 `prompt_engine.models/strategies/knowledge`**，运行时完全解耦。
- **技术机制复刻**（架构相同、实现独立）：Optimizer 编排（双级缓存 → 低创意模板直出 → 策略注册表 → system prompt → context 注入 → RAG few-shot → LLM 多候选 → 结构化后处理）、策略 `@register` 注册表、RAG TF-IDF 向量库、LLM 供应商、结构化视频输出。
- **视频关键词库**：从 7 个参考仓库构建视频专属知识库——
  - img-prompt：5040 标签 → 视频维度关键词词典（动作/运镜/光影/色彩/风格/镜头/场景）
  - awesome-video-prompts：50 个结构化 JSON 视频提示词 → few-shot 高质量种子
  - seedance2-skill / awesome-seedance / awesome-seedance-2-prompts：平台策略指令与商用用例提示词
  - drama-skills：短剧分镜/视频提示词工作流模板
  - stable-diffusion-videos：动画技术参考（不直接入库）
- **API**：`/v1/video/optimize`、`/v1/video/optimize/batch`（上限 20、有界并发）、`/v1/video/platforms`、`/v1/video/keywords`、`/health`。
- **不迁移既有 domain=video 分支**（保留兼容），但文档明确独立引擎为视频优化的正式落点。

## Capabilities

- **New**: `video-prompt-engine`（独立视频引擎：策略/知识库/服务/关键词库）

## Impact

- 新增 `video_prompt_engine/` 包（models/strategies/optimizer/llm/knowledge/api/config）
- 新增视频知识库种子（`video_prompt_engine/knowledge/seed_video_prompts.json` + 关键词词典），构建脚本 `video_prompt_engine/knowledge/build.py`
- 图片 `prompt_engine/` **零改动**（不 import、不修改）
- Multi-Publish 侧：文档标注独立引擎（后续 videogen 集成切换 8020 为可选迁移，本次不强制）
