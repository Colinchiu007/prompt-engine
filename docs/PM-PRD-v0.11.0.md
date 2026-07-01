# PM-PRD v0.11.0 — 用户掌控优化（关键词 + 风格 + 扩写）

## 概述

3 个后端已实现但 UI 未暴露的功能一次性交付：
1. **关键词注入可视化** — Workbench 新增「关键词注入」面板，显示/手动触发 keyword_injector
2. **25 风格维度选择器** — 优化前可手动指定风格，而非仅 auto-detect
3. **扩写 UI** — 简写 prompt 一键扩写（复用 `/v1/rewrite` 端点）

## 背景

用户当前 Workbench 只有「优化 / 分类 / 评估」3 个按钮，`keyword_injector.py`、`models.py` 的 StyleCategory 枚举、`/v1/rewrite` 端点全部闲置。用户无法干预优化过程（风格、关键词、扩写）。

## 功能清单

| 功能 | 等级 | 描述 | 工作量 |
|------|------|------|--------|
| **F1 关键词注入** | P0 | Workbench 显示已注入的关键词 + 开关切换 | 小 |
| **F2 风格选择** | P1 | 优化前可选 25 个 StyleCategory | 中 |
| **F3 扩写** | P1 | 输入简短 prompt → 一键扩写(rewrite) | 小 |

## F1: 关键词注入可视化

### 目标
Workbench 优化结果下方增加「关键词注入」面板，显示 keyword_injector 注入的关键词列表 + 手动切换开关。

### 交互
```
[优化结果: A majestic feline...]
[耗时: 1234ms] [平台: midjourney] 

▼ 关键词注入 (12 个词)
  majestic, royal, velvet, golden, dramatic, cinematic...  [显示全部]
  [✓ 启用注入] [刷新]
  
[风格: 自动检测 → landscape ▼]   [扩写: 输入简短 prompt...]  [扩写]
```

### 端点
`GET /v1/keywords` — 7 平台返回平台相关的 MJ 关键词列表
`POST /v1/classify` (无需功能变更 — 已返回关键词)

### 数据
- `keyword_injector.inject_style_keywords()` 已可用
- `keyword_injector.load_mj_style_db()` 已加载 2100+ 关键词

## F2: 风格维度选择器

### 目标
优化/分类前用户可选 25 个 StyleCategory，而非仅 auto-detect。

### 交互
```
[选择风格: 自动检测 ▼]
           ┌─────────────┐
           │ design      │
           │ digital     │
           │ photography │
           │ fantasy     │
           │ ... 25 个    │
           └─────────────┘
```

### 端点
`GET /v1/styles/categories` — 已有，返回 25 风格

## F3: 扩写 UI

### 目标
Workbench 增加「扩写」按钮 + 独立文本框，输入简短 prompt → rewrite 端点 → 扩写到 300 词

### 交互
```
[扩写区]
[输入: a cat              ] [扩写]
[结果: A majestic feline sitting gracefully...]
```

### 端点
`POST /v1/rewrite` — 已有

## 验收

| F | 标准 |
|---|------|
| F1 | 优化结果下显示关键词列表 + 开关 |
| F1 | 关闭后优化应无关键词 |
| F2 | 25 风格可选，选中后优化结果可能包含风格相关内容 |
| F3 | 输入 "a cat" 点击扩写 → 返回 >200 词的优化 prompt |

## 风险

| 风险 | 缓解 |
|------|------|
| 关键词显示太多（2100+） | 优化后仅显示已注入的（通常 10-20 个） |
| 风格选择 + auto-detect 冲突 | 手动选择覆盖 auto-detect |
| rewrite 只返回 <300 词 | 端点已实现 max_length=300，不会更长 |
