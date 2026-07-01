# PM-PRD v0.13.0 — README 英文版 + GitHub 徽章 + PyPI 发布

## 概述

开源推广三件套：英文文档 + CI 状态 + pip 安装。

## 背景

项目已经 12 个版本迭代、207 个测试、完整功能，但：
- **README 只有中文** — 海外用户/英文社区无法理解
- **无 PyPI 包** — 用户无法 `pip install prompt-engine`
- **无 CI 徽章** — 别人看仓库不知道测试状态

## 功能清单

| 功能 | 等级 | 工作量 |
|------|------|--------|
| F1 README 英文版 | P1 | 中（翻译+重构） |
| F2 PyPI 发布配置 | P1 | 小（setup.py/pyproject.toml） |
| F3 GitHub Actions 徽章 | P1 | 极小 |

## F1: README 英文版

保留中文 README 不变。新增 `README.en.md`，内容结构：
- What is Prompt Engine?
- Features (7 platforms, 25 dimensions, RAG, DSL, etc.)
- Quick Start (install → run → optimize)
- API Reference (REST endpoints)
- Configuration
- Screenshots (TBD)
- Contributing

说明流程：

## F2: PyPI

`pyproject.toml` 已存在，补充：
- `name = "prompt-engine-image"`（避免被占用）
- `readme = "README.md"` → 发布时改为 en
- `license = "MIT"`
- `classifiers` 填分类

## F3: GitHub Actions 徽章

在 README.en.md / README.md 顶部加：
```markdown
[![Tests](https://github.com/Colinchiu007/prompt-engine/actions/workflows/test.yml/badge.svg)](https://github.com/Colinchiu007/prompt-engine/actions)
```

## 交付标准

- [ ] `README.en.md` 完整英文文档
- [ ] 中文 README 顶部加中文说明 + 徽章
- [ ] `pyproject.toml` PyPI 配置
- [ ] GitHub Actions 徽章可显示