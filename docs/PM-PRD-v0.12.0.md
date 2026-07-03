# PM-PRD v0.12.0 — 反馈闭环 UI + 扰动增强 UI

## 概述

两个已经存在完整后端的端点，核心能力全部就绪但前端从未暴露。

## 背景

| 功能 | 后端状态 | 前端状态 |
|------|---------|---------|
| **反馈闭环** | `POST /v1/feedback` + `GET /v1/feedback/stats` + `GET /v1/feedback/recent` + `POST /v1/feedback/apply` 4 个端点完整 | ❌ 无 UI |
| **扰动增强** | `POST /v1/disturb-optimize` 端点完整（Infinity BSC 扰動+优化取最佳） | ❌ 无 UI |

## 功能清单

| 功能 | 等级 | 工作量 | 描述 |
|------|------|--------|------|
| **F1 反馈闭环 UI** | P1 | 中 | Workbench 优化结果下方加赞/踩按钮 + 反馈历史页 |
| **F2 扰动增强 UI** | P1 | 小 | Workbench 增加「A/B 多版本」按钮 |

## F1: 反馈闭环 UI

### 交互

```
[优化结果]
  A majestic feline...
  [👍] [👎] [提交反馈]  ← 新增

[反馈历史]
  最近 10 条反馈：
  ↓
  赞: "a cat" → "A majestic feline..."
  踩: "sunset" → "..."（重复，建议换平台）
```

### 端点

| 端点 | 作用 | 前端调用时机 |
|------|------|-------------|
| `POST /v1/feedback` | 提交赞/踩 | 用户点击赞/踩后 |
| `GET /v1/feedback/stats` | 查看总统计 | Settings 页面 |
| `GET /v1/feedback/recent` | 最近 N 条 | Settings 页面 |
| `POST /v1/feedback/apply` | 应用反馈调整权重 | Settings 页按钮 |

## F2: 扰动增强 UI

### 交互

```
[优化 Prompt] [A/B 多版本]  ← 新增按钮
  ↓ 点击 A/B 多版本
[三个版本对比]
  #1: A majestic feline...(1234ms)
  #2: A regal cat on a...(1567ms)  [最佳]
  #3: A cat in soft...(1112ms)
  [→ 选本版本] [📋 复制]
```

### 端点

| 端点 | 作用 |
|------|------|
| `POST /v1/disturb-optimize` | 扰动后优化取最佳 |

## 验收

- [x] 优化结果下方有赞/踩按钮
- [x] 点击赞/踩后调用 `/v1/feedback`
- [x] Settings 显示反馈统计 + 最近反馈
- [x] "应用反馈"按钮可调 `/v1/feedback/apply`
- [x] Workbench 有「A/B 多版本」按钮
- [x] 点击后显示 3 个版本对比
- [x] 每个版本可「选用」或「复制」
- [x] 203 测试通过