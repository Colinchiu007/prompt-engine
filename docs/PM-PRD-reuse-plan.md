# PM-PRD：awesome-gpt-image-2 三件套复用计划

## 概述

将 awesome-gpt-image-2 的三个高复用价值组件集成到 prompt-engine 中。

| 功能 | 等级 | 工作内容 | 预估工作量 |
|------|------|---------|-----------|
| **F1: Agent Skill 分发** | ⭐⭐⭐ | 为 prompt-engine 导出 SKILL.md + install 脚本 | 小 |
| **F2: 506 案例注入 RAG** | ⭐⭐⭐ | 解析 cases.json → 注入 RAG 种子数据 | 中 |
| **F3: Prompt-as-Code 模板** | ⭐⭐ | 结构化 prompt 块模板系统 | 中 |

## 依赖关系

```
F1 (SKILL.md) ── 无依赖 ── 可最先做
F2 (RAG 注入) ── 无依赖 ── 可与 F1 并行
F3 (Prompt-as-Code) ── 依赖 F2? 不直接依赖
```

3 个功能互不依赖，可按顺序逐个实现。

## 执行顺序

1. **F1: Agent Skill** — 新建 `agents/skills/prompt-engine/SKILL.md` + install 脚本
2. **F2: RAG 注入** — 解析 `cases.json` prompt 数据 → 写入 RAG 知识库
3. **F3: Prompt-as-Code Schema** — 设计结构化 prompt 模板系统

## 每个功能的输出

| 功能 | 架构文档 | 测试文件 | 代码改动 |
|------|---------|---------|---------|
| F1 | `ARCH-F1-agent-skill.md` | 无（纯文档） | 新建 `agents/skills/prompt-engine/` 目录 |
| F2 | `ARCH-F2-rag-seed.md` | `tests/test_rag_seed.py` | `prompt_engine/knowledge/` 增加导入 |
| F3 | `ARCH-F3-prompt-template.md` | `tests/test_prompt_template.py` | 新建 `prompt_engine/template_engine.py` |

## 更新文档清单

- [ ] CHANGELOG.md — 新增功能记录
- [ ] README.md — 特性列表 + 使用说明
- [ ] docs/AGENTS.md — 新增 SKILL 安装路径
