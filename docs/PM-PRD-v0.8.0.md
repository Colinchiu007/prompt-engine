# PM-PRD: 资源展示 + 图片预览 + 模型配置

## 概述

3 个修复/增强，针对当前 v0.7.0 看板的 3 个问题：

| 功能 | 描述 | 工作量 |
|------|------|--------|
| **F1: 资源展示** | Dashboard 展示引擎资源（数据/词库/案例/平台等），不再空着 | 小 |
| **F2: 图片预览** | 优化 prompt 后直接生成图片预览，多模型可选 | 中 |
| **F3: 模型 API 配置** | 配置面板添加图片模型 API 预设（DALL-E/StableDiffusion/Replicate/xflux） | 中 |

## F1: 资源展示（Dashboard）

Dashboard 增加「引擎资源」卡片：
- 平台策略：7 个
- RAG 案例：1556 条（506+1050）
- MJ 关键词：2100+
- DSL 通配符：10 类 100+ 值
- 风格维度：25 维
- LLM 供应商：3 个
- 模板：EN/ZH 模板

## F2: 图片预览（Workbench）

在 Workbench 优化结果下方增加「图片预览」按钮组：
- 选模型 → 调生成 API → 显示图片
- 预设模型：DALL-E 3, Stable Diffusion, Flux, Imagen, Pollinations
- 不需要新 API Key 的：Pollinations（免费）
- 缓存预览（避免重复生成）

## F3: 模型 API 配置（Settings）

新增「图片生成 API」卡片：
- API Key 配置：OpenAI / Replicate / Stability / Together / xai
- 预设模型清单（10+ 主流模型）
- 模型 ID 说明
- 测试按钮
