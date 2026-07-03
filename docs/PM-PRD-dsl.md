# PM-PRD: sd-dynamic-prompts 三件套复用计划

## 概述

借鉴 sd-dynamic-prompts (2276⭐) 的模板 DSL、四层架构、通配符系统，增强 prompt-engine 的 F1 模板驱动优化能力。

| 功能 | 等级 | 工作内容 | 预估工作量 |
|------|------|---------|-----------|
| **F1: 模板语法 DSL** | ⭐⭐⭐ | 实现 `{option1|option2}` 变体 + `__wildcard__` 通配符 + `N$$` 数量限定语法解析器 | 中 |
| **F2: 四层架构** | ⭐⭐⭐ | Parser → Command AST → Sampler → Generator 四层重构 template_engine.py | 中 |
| **F3: Wildcard 文件系统** | ⭐⭐ | `__filename__` 从文件/关键词池读取随机值 | 小 |

## 依赖关系

```
F1 (语法解析器) ── F2 (四层架构需要 F1) ── F3 (通配符需要 F2)
```

有严格依赖关系，必须按 F1→F2→F3 顺序执行。

## 执行顺序

1. **F1: 模板语法 DSL** — 新建 `prompt_engine/dsl_parser.py`，实现 `{a|b|c}` / `__wild__` / `N$$opt` 解析
2. **F2: 四层架构** — 重构 `template_engine.py`，引入 Parser→AST→Sampler→Generator
3. **F3: Wildcard 文件系统** — 实现 `__filename__` 从关键词池/YAML 文件读取随机值

## 更新文档

- [ ] CHANGELOG.md
- [ ] README.md
- [ ] docs/PRD.md
- [ ] docs/AGENTS.md
