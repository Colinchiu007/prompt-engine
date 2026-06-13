# ARCH: Prompt Engine 全功能看板

## 方案

FastAPI 内嵌 Vue 3 SPA，单部署。

## 目录结构

```
prompt_engine/
├── web/                  # Vue 3 前端
│   ├── index.html        # 入口页面
│   ├── src/
│   │   ├── App.vue       # 根组件（路由）
│   │   ├── api/          # REST API 调用层
│   │   ├── views/
│   │   │   ├── Workbench.vue    # P1 — Prompt 工作台
│   │   │   ├── Dashboard.vue    # P2 — 数据看板
│   │   │   └── Settings.vue     # P3 — 配置 + 监控
│   │   └── utils/
```

## 数据流

```
Vue 3 UI ──HTTP──→ FastAPI REST (已有 14 端点)
                      │
                      ↓
                 prompt_engine 核心
```

## 路由

| 路径 | 视图 | 功能 |
|------|------|------|
| `/` | Workbench | Prompt 输入→优化→分类→评估 |
| `/dashboard` | Dashboard | 调用统计/分类分布/平台分布/反馈趋势 |
| `/settings` | Settings | 策略配置/通配符管理/供应商切换/日志 |

## 部署

```bash
python -m uvicorn prompt_engine.api.rest:app  # 自带 /static/ 路由提供前端
```

## 迭代顺序

| 迭代 | 文件 | 测试数 |
|------|------|--------|
| P1 | `web/` Workbench + `api/` 统计端点 | 6 |
| P2 | Dashboard ECharts | 4 |
| P3 | Settings + 日志 | 4 |

**总新增测试：~14**
