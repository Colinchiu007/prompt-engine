# ARCH-F11: 25 风格维度选择器

## 目标
优化/分类前用户可选 StyleCategory，而非仅 auto-detect

## 设计

### 端点
**现有** `GET /v1/styles/categories` — 返回 25 个 StyleCategory
```json
{
  "categories": [
    {"id": 1, "name": "design_styles", "description": "设计风格"},
    ...
  ],
  "count": 25
}
```

### 前端变更

#### 风格选择器
Workbench 优化按钮左侧新增 el-select：

```
[自动检测 ▼] ┌─────────────────┐  ← 新增
             │ 自动检测         │
             │ design_styles    │
             │ digital          │
             │ photography      │
             │ fantasy_art      │
             │ ...              │
             └─────────────────┘
```

#### 逻辑
- 选择「自动检测」（默认）→ 走现有 auto-detect（classifier）
- 选择任何风格 → 传 `style` 参数到 `/v1/optimize`

### 数据流
```
用户选择 "fantasy_art"
   ↓
POST /v1/optimize { prompt: "a cat", platform: "midjourney", style: "fantasy_art" }
   ↓
optimizer 跳过 auto-detect → 用指定 style 构建 system_prompt
   ↓
返回优化结果
```

### 关键决策
| 决策 | 原因 |
|------|------|
| **el-select 而非 el-tree** | 25 项，一行即可 |
| **不分组** | 25 项直接列出比分组更快 |
| **中英文混合显示** | `fantasy_art — 幻想艺术` |