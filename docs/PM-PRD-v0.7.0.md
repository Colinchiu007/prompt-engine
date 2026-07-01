# PM-PRD: prompt-optimizer 三件套复用计划

## 概述

将 prompt-optimizer 的三个高价值设计模式集成到 prompt-engine 中。

| 功能 | 等级 | 工作内容 | 预估工作量 |
|------|------|---------|-----------|
| **F1: 模板驱动优化** | ⭐⭐⭐ | 将策略代码中的 LLM 指令抽取为独立模板文件，EN/ZH 双语 | 中 |
| **F2: 多模型供应商** | ⭐⭐⭐ | 扩展 adapter 层，新增 DeepSeek / Gemini / Grok 等供应商 | 小 |
| **F3: 评估对比模式** | ⭐⭐ | 新增优化结果的评估和对比能力 | 中 |

## 依赖关系

```
F1 (模板) ── 无依赖 ── 可最先做
F2 (供应商) ── 无依赖 ── 可与 F1 并行
F3 (评估) ── 依赖 F1？不直接依赖
```

3 个功能互不依赖，可按顺序逐个实现。

## 执行顺序

1. **F1: 模板驱动优化** — 新建 `prompt_engine/templates/prompts/` 目录，将各策略 `build_system_prompt()` 中的 LLM 指令抽取为独立 `.yaml` 模板文件
2. **F2: 多模型供应商** — 扩展 `prompt_engine/llm/`，新增 DeepSeek、Gemini、SiliconFlow 供应商
3. **F3: 评估对比** — 新增 `POST /v1/evaluate` 端点 + 对比评估能力

## 更新文档

- [ ] CHANGELOG.md — v0.7.0
- [ ] README.md — 特性列表 + 新供应商
- [ ] docs/PRD.md
- [ ] docs/AGENTS.md
