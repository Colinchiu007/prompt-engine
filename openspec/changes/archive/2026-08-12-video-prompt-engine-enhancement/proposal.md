# video-prompt-engine-enhancement — 视频提示词引擎全面增强

## Why

独立视频引擎（8020）已上线并通过真实 LLM 验证，但存在差距：知识库太小（11 条种子，RAG few-shot 实际未命中）、结构化输出失败无重试、仅 2 个平台策略、无持久缓存、无评估/反馈闭环、无中文输出、videogen 未集成。

## What Changes

- **知识库全量扩充**：从 7 开源仓库提取 100-300 条视频种子（awesome-video-prompts 全量、awesome-seedance 商用用例、drama-skills 分镜、seedance2-skill 语法案例）；按平台分层；关键词命中触发检索兜底
- **结构化输出重试**：JSON 解析失败带提示重试（≤2 次），耗尽才回退原文
- **多平台专项策略**：veo/kling/hailuo/doubao 平台能力差异（运镜/时长/风格约束）
- **SQLite 双级缓存**：内存 + SQLite 持久（复刻图片引擎 CacheManager）
- **输入自动分类**：题材/镜头意图检测 → 自动选策略与关键词维度
- **评估与反馈闭环**：evaluator（保真度/六要素/镜头字段/长度）+ feedback 沉淀
- **中文输出支持**：output_language 参数（zh/en，默认 en；zh 保留中文 + 镜头术语双语）
- **videogen 集成**：Multi-Publish videogen 切换 8020 独立引擎（可选配置，默认回退兼容）

## Capabilities

- **Modified**: `video-prompt-engine`（知识库/重试/多平台/缓存/评估/反馈/中文/集成增强）

## Impact

- prompt-engine 仓库：video_prompt_engine/ 多文件增强 + 知识库数据扩充
- Multi-Publish：videogen-stages/contract 切换 8020（可选配置）
- 测试：视频引擎单测扩充 + videogen 切换契约测试
