# PM-PRD v0.9.1 — Dashboard 测试数据填充

## 概述

Dashboard 首次打开时统计卡片为 0、ECharts 显示「暂无数据」——因为还没有任何真实 API 调用。新功能：自动填充种子数据，确保 Dashboard 首次打开即有数据显示。

## 背景

| 问题 | 用户反馈 | 影响 |
|------|---------|------|
| 统计卡片全部为 0 | "数据看板下面还是空的" | 新用户以为功能坏了 |
| ECharts 无数据 | "分类分布/平台分布是空的" | 无法验证 UI 布局 |
| 测试数据填充 | 希望「不走真实 API」也有数 | 开发/演示阶段 |

## 功能清单

| 功能 | 等级 | 描述 | 工作量 |
|------|------|------|--------|
| **F1 启动种子** | P1 | API 启动时自动生成 50 条模拟数据 | 小 |
| **F2 前端加载** | P1 | Dashboard 从 stats 端点读取，有数即展示 | 小 |
| **F3 开发端点** | P2 | POST /v1/dev/seed 重新填充种子数据 | 中 |

## 方案

### 种子数据（50 条模拟记录）

| 字段 | 模拟方式 | 示例 |
|------|---------|------|
| platform | 轮询 7 个平台 | midjourney (20), sd (10), ... |
| prompt | 5 个示例 prompt 随机 | "a majestic cat", "cyberpunk city" |
| category | 25 风格随机取 1-3 个 | digital 15%, design 12%, nature 8% |
| duration_ms | 正态分布 500-3000ms | 1243ms |
| success | 95% success, 5% fail | ✅ 48, ❌ 2 |
| timestamp | 过去 24h 均匀分布 | 2026-06-13 14:23 |

### 后端改动

- `prompt_engine/api/stats_store.py` — 启动时 seed
- `POST /v1/dev/seed` — 手动重新 seed

### 前端改动

- Dashboard 已正确读取 `/v1/stats/*` 端点
- 种子数据写满后端 → 前端自动显示
