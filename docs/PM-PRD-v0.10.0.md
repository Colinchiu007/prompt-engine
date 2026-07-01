# PM-PRD v0.10.0 — 工程化 + 批量优化

## 概述

P0 三件套：项目工程化补齐 + 用户高频需求。

## 背景

项目 011 经历了 9 个版本迭代（v0.3.1 → v0.9.4），核心功能已完整。
但生产化指标仍有缺口：
1. **Dockerfile 缺失** — 团队/用户部署困难
2. **CI 缺失** — PR 没有自动验证
3. **批量 UI 缺失** — 后端 `/v1/optimize/batch` 端点闲置

## 功能清单

| 功能 | 等级 | 描述 | 工作量 |
|------|------|------|--------|
| **F1 Dockerfile + docker-compose** | P0 | 一键启动整个项目（含 uvicorn + Web） | 小 |
| **F2 GitHub Actions CI** | P0 | PR 自动跑 203 个测试 | 小 |
| **F3 批量优化 UI** | P0 | Workbench 支持一次提交 N 个 prompt | 中 |

## F1: Dockerfile

### 目标
```bash
docker-compose up
# → uvicorn 8000 + 内置 Web UI
# → 零本地依赖
```

### 关键决策
- **基础镜像**：`python:3.11-slim`（平衡大小与兼容性）
- **依赖管理**：使用 `requirements.txt`（已存在）
- **无 LLM Key 也能跑**：基础模式（mock 优化）
- **缓存层**：分阶段 COPY，先装依赖再 COPY 源码

### 端点
无新增。

## F2: GitHub Actions CI

### 目标
PR 推送到 GitHub → 自动跑 203 个测试 → 红绿灯 ✅ / ❌

### 工作流
1. **lint** — Python 语法检查（可选）
2. **test** — `pytest tests/ -q` 跑全量测试
3. **build** — Dockerfile build 测试（可选）

### 关键决策
- **触发**：`push` + `pull_request` 到 master
- **Python 版本**：`3.11`（项目实际用的版本）
- **超时**：5 分钟（测试通常 30s 内完成）
- **缓存**：pip 缓存（加速）

## F3: 批量优化 UI

### 目标
Workbench 增加「批量模式」：用户可以一次粘贴多行 prompt，每行一个，点击「批量优化」返回 N 个结果。

### 交互流程
```
[textarea: a cat\ncyberpunk city\n...] 
   ↓ 点「批量优化」
[加载: 3/3 完成]
[结果列表: #1 a majestic feline..., #2 neon-lit...]
   ↓ 展开
[每行可单独下载/复制]
```

### 端点
复用现有 `POST /v1/optimize/batch`（已实现）：
```json
{
  "requests": [
    {"prompt": "a cat", "platform": "midjourney"},
    {"prompt": "cyberpunk city", "platform": "midjourney"}
  ]
}
```

返回：
```json
[
  {"optimized_prompt": "...", "duration_ms": 1200, ...},
  ...
]
```

### 关键决策
- **每行一个 prompt**：用换行分割（不依赖 CSV）
- **最大 10 个/批**：避免 LLM 配额爆炸
- **进度显示**：每个完成更新进度条
- **失败隔离**：一条失败不影响其他
- **同一平台**：避免下拉框在循环中切换

## 验收

| 项 | 标准 |
|------|------|
| F1 | `docker build .` 成功；`docker run -p 8000:8000` 可访问 |
| F2 | PR 推 master 自动跑测试，状态显示在 PR |
| F3 | 输入 3 行 → 输出 3 个结果，每条独立显示 |

## 风险

| 风险 | 缓解 |
|------|------|
| Dockerfile 镜像大 | 用 slim + 多阶段 |
| CI 资源用尽 | cache pip + 限并发 1 |
| 批量调用超时 | 单批上限 10 + 并发 3 |
