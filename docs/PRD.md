# Prompt Engine — PRD v0.5.0

> 项目 011：图片生成提示词优化引擎
> 状态：已交付 | 迭代周期：s1-s5 + P0-P4

---

## 1. 产品概述

### 1.1 一句话定义

将用户原始提示词自动优化为适合主流 AI 图片生成平台（Midjourney / Stable Diffusion / DALL·E / 通义万相 / 文心一格 / 即梦）的高质量提示词，并提供 25 维 MJ 风格分类能力。

### 1.2 目标用户

- **AI 绘画创作者** — 需要跨平台发布高质量 prompt 的用户
- **内容团队** — 统一管理多平台图片生成风格
- **Prompt 工程师** — 需要批量优化/分类 prompt 的专业用户

### 1.3 核心竞争力

1. **自建分类引擎** — 关键词 + 向量 + LLM 三级流水线，不依赖第三方分类 API
2. **闭环学习** — 用户反馈 → 权重调整 → 分类精度持续提升
3. **跨平台一致** — MJ/SD/DALL·E 等 7 平台共享风格数据库和分类体系

---

## 2. 技术架构

### 2.1 系统分层

```
┌─────────────────────────────────────────────────────┐
│                   集成层                               │
│  Python SDK    REST API    MCP Server    CLI          │
├─────────────────────────────────────────────────────┤
│                   编排层                               │
│  Optimizer (optimize/reverse/rewrite/disturb)        │
├──────────────┬──────────────────────────────────────┤
│  分类流水线    │  优化流水线                            │
│  keyword_match│  per-platform strategy                 │
│  ↓            │  (MJ/SD/DALL·E/Tongyi/Yizhang/Jimeng) │
│  vector_rag   │  + keyword injection                   │
│  ↓            │                                        │
│  llm_fallback │                                        │
├──────────────┴──────────────────────────────────────┤
│                   数据层                                │
│  MJ Style DB (25维)  │  Feedback Store  │  Weights    │
│  RAG Vector Index      │  Style Templates   │  Config     │
└─────────────────────────────────────────────────────┘
```

### 2.2 分类流水线

```
prompt → keyword_match ──conf≥0.6──→ return (fast path)
            ↓ conf<0.6
         vector_rag ────has_result──→ return (semantic path)
            ↓ no result
         llm_classify ──────────────→ return (fallback path)
```

### 2.3 反馈闭环

```
user submit feedback (rating + corrected categories)
            ↓
    _apply_feedback_to_weights()
            ↓
    keyword_weights.json updated
            ↓
    next classify request loads new weights
            ↓
    accuracy improves over time
```

---

## 3. 功能清单

### 3.1 核心功能

| 功能 | 优先级 | 状态 | 说明 |
|------|--------|------|------|
| 多平台 prompt 优化 | P0 | ✅ | 7 平台（MJ/SD/DALL·E/通义/文心/即梦/通用） |
| 风格分类（25 维） | P0 | ✅ | 关键词+向量+LLM 三级流水线 |
| 逆向量分类 | P0 | ✅ | 图片 URL → prompt 分析 |
| Prompt 扩写 | P1 | ✅ | 简短描述 → 详细 prompt |
| 扰动增强优化 | P1 | ✅ | 多版本择优 |
| A/B 多候选 | P1 | ✅ | 一次生成多个版本 |
| 批量优化 | P1 | ✅ | 最多 10 条/次 |

### 3.2 分类能力

| 功能 | 优先级 | 状态 | 说明 |
|------|--------|------|------|
| 关键词匹配（同义词） | P0 | ✅ | 中文+英文，~0ms |
| 向量语义搜索 | P1 | ✅ | TF-IDF，~50ms |
| LLM 零样本分类 | P1 | ✅ | 语义理解兜底 |
| RAG 增强索引 | P1 | ✅ | 500 特征 char_wb 分析器 |
| 风格推荐 | P1 | ✅ | StyleType → StyleCategory 映射 |
| 反馈驱动权重 | P2 | ✅ | 用户反馈 → 关键词权重自动调整 |

### 3.3 集成方式

| 方式 | 状态 | 说明 |
|------|------|------|
| Python SDK | ✅ | from prompt_engine import Optimizer |
| REST API | ✅ | 12 个端点，FastAPI |
| MCP Server | ✅ | Model Context Protocol |
| CLI | ✅ | prompt-engine classify/categories/optimize/recommend/feedback |

### 3.4 数据闭环

| 功能 | 状态 | 说明 |
|------|------|------|
| 反馈收集 | ✅ | FeedbackEntry → feedback_db.json |
| 反馈统计 | ✅ | 按方法、评分分布统计 |
| 权重自动调整 | ✅ | _apply_feedback_to_weights() |
| 权重持久化 | ✅ | keyword_weights.json |

---

## 4. 竞品分析

### 4.1 对标产品

| 产品 | 方向 | 对比 |
|------|------|------|
| PromptBase | Prompt 交易市场 | **非竞品** — 我们是引擎，他们是市场 |
| PromptHero | Prompt 搜索+分享 | **差异化** — 我们提供分类和优化，不仅是搜索 |
| Infinity (GitHub) | Prompt 优化工具 | **来源** — 复用其 rewriter/BSC/IVC 设计模式 |
| MJ Styles Reference | 风格关键词库 | **数据源** — 6000+ star 开源项目 |

### 4.2 竞争壁垒

1. **三级流水线** — 唯一同时支持关键词+向量+LLM 的 prompt 分类引擎
2. **反馈闭环** — 竞品都是单向分类，无学习能力
3. **跨平台一致性** — 同一风格分类体系覆盖 7 个生成平台

---

## 5. 数据模型

### 5.1 核心实体

```
StyleCategory (25 维)
    ├── design_styles / digital / experimental
    ├── lighting / material_properties / materials / dimensionality
    ├── colors_and_palettes / combinations
    ├── camera / perspective / structural_modification
    ├── nature_and_animals / objects / outer_space
    ├── geometry / geography_and_culture
    ├── drawing_and_art_mediums / sfx_and_shaders
    ├── themes / intangibles / tv_and_movies / song_lyrics
    └── emojis / miscellaneous

StyleType (14 种)
    └── realistic / cartoon / anime / oil_painting / watercolor / pixel
        cyberpunk / fantasy / photography / 3d_render / minimalist
        abstract / portrait / landscape

StyleCategoryResult
    ├── categories: StyleCategory[]
    ├── method: keyword_match | vector_rag | llm_classify
    └── confidence: float

FeedbackEntry
    ├── prompt, detected_categories, corrected_categories
    ├── rating: 0-5
    └── method, confidence
```

---

## 6. 测试策略

- **127 个测试用例**，100% mock 隔离
- 无需真实 API Key
- 覆盖：分类器（30）、策略（17+14）、优化器（5）、A/B（3）、反馈（6+4）、RAG（6）、反向推荐（5）
- 运行时间：~25s

---

## 7. 迭代历史

### s1-s5: 核心功能

| 迭代 | 内容 | 时间 |
|------|------|------|
| s1 | MJ 竞品分析、数据源调研 | Day 1 |
| s2 | MJ 风格数据库集成（2100+ 关键词） | Day 1-2 |
| s3 | 风格分类器构建（关键词+LLM 双路径） | Day 2-3 |
| s4 | REST API + MCP Server 暴露 | Day 3 |
| s5 | 风格感知关键词注入 | Day 3-4 |

### P0-P4: 增强功能

| 阶段 | 内容 | 时间 |
|------|------|------|
| P0 | 跨平台风格注入 | Day 4 |
| P1 | RAG 增强 + 反向推荐 | Day 4-5 |
| P2 | CLI + README | Day 5 |
| P3 | 用户反馈循环 | Day 5 |
| P4 | 反馈驱动权重 | Day 5-6 |

---

## 8. 后续方向（未纳入当前版本）

| 方向 | 说明 | 预计难度 |
|------|------|---------|
| 比特级分类器集成 | 用 PyTorch 训练分类器替换关键词匹配 | 高（需标注数据） |
| 在线学习 | 权重更新后无需重启，实时生效 | 低 |
| 分类结果可视化 | 雷达图/热力图展示 25 维结果 | 中 |
| 多语言 prompt 分类 | 扩展非中英文场景 | 中 |
| Web UI | 基于 FastAPI 的管理界面 | 中 |

---

## 9. 风险与限制

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| MJ 数据库不更新 | 关键词可能过时 | 用户反馈权重可补偿 |
| TF-IDF 精度上限 | 中文语义理解不如 embedding | 预留 embedding 接口 |
| 反馈数据稀疏 | 权重调整效果有限 | 默认权重 1.0，安全回退 |
