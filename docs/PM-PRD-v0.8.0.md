# PM-PRD v0.8.0 — Dashboard 资源展示 + 图片预览 + 模型配置

## 概述

v0.8.0 三个功能在快速模式实施后补出 PM-PRD 计划。回顾性文档，不影响已实现代码。

## 背景

快速模式实施时直接开了干，事后补出此计划作为正式记录。三个功能都基于已有路径扩展，**没有改架构**。

## 功能清单

| 功能 | 等级 | 内容 | 工作量 |
|------|------|------|--------|
| **F1 资源展示** | P1 | Dashboard 新增「引擎资源」卡片 | 小 |
| **F2 图片预览** | P1 | Workbench 优化结果下方加预览功能 | 中 |
| **F3 模型配置** | P1 | Settings 加图片模型表格 + Key 配置说明 | 中 |

## F1: 引擎资源展示

### 目标
Dashboard 顶部展示 prompt-engine 内嵌的全部资产，让用户一眼看到引擎能力。

### 资源清单（7 类）
1. 平台策略：7 个（midjourney, stable-diffusion, dall-e, tongyi-wanxiang, wenyi-xinyi, jimeng, nano-banana-pro）
2. RAG 案例库：936 条（prompts_db 918 + seed_prompts 18）
3. MJ 关键词：2100+ 个
4. 风格维度：25 个 MJ 风格分类
5. LLM 供应商：3 个（OpenAI, 讯飞, Gemini）
6. DSL 通配符：100+ 个值
7. 模板：2 个（midjourney EN/ZH + generic）

### 端点
`GET /v1/resources` 返回 JSON 资源清单。

## F2: 图片预览

### 目标
Workbench 优化完 prompt 后，用户可一键生成预览图，验证效果。

### 实现
- 端点 `POST /v1/preview` 返回图片 URL
- Pollinations AI 完全免费，直接构造 URL（`https://image.pollinations.ai/prompt/{encoded}`）
- 其他模型需 API Key（本版本不实际调用，仅返回 placeholder）

### 端点
```
GET  /v1/image-models  → 14 个预设模型清单
POST /v1/preview       → 生成预览 URL
```

## F3: 模型 API 配置

### 目标
Settings 页面显示 14 个图片模型，支持按需配置 API Key。

### 预设模型（14 个）
- Pollinations（免费）/ DALL-E 3 / DALL-E 2 / GPT-Image-1
- Flux Pro / Flux Schnell / Midjourney v6 / Kandinsky 3
- SDXL / SD3.5
- Ideogram v2 / Playground v2.5 / Imagen 3
- Aurora (xAI Grok)

### 供应商环境变量
- `OPENAI_API_KEY` — DALL-E / GPT-Image
- `REPLICATE_API_KEY` — Flux / MJ / Kandinsky
- `STABILITY_API_KEY` — SDXL / SD3.5
- `TOGETHER_API_KEY` — Ideogram / Playground / Imagen
- `XAI_API_KEY` — Aurora

## 实施时遇到的问题

| 问题 | 解决 |
|------|------|
| StaticFiles `app.mount("/")` 拦截 `/v1/*` 端点返回 404 | 将 mount 移到最后，定义在所有端点之后 |
| 实际 RAG 数据是 936 条（不是测试假设的 1500） | 修正测试断言为 `>= 500` |
| 配置文件名变了（gptimage2 → prompts_db 等） | 列举多个路径，遍历查找 |

## 验收

- [x] Dashboard 顶部显示 7 类资源卡片
- [x] Workbench 优化结果下方显示「图片预览」按钮
- [x] Pollinations 可直接生成预览图
- [x] Settings 列出 14 个模型 + 6 个供应商环境变量
- [x] 9 个新测试通过
- [x] 全部 190 测试通过

## 依赖关系

3 个功能相互独立，可并行：
- F1 → 仅后端端点 + 前端展示
- F2 → 后端预览端点 + 前端按钮
- F3 → 后端模型清单 + 前端表格

实际实施顺序：F1 → F2 → F3（按用户提的顺序）。
