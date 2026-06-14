# ARCH-F10: 关键词注入可视化

## 目标
Workbench 优化结果下方显示 keyword_injector 注入的关键词列表 + 开关

## 设计

### 端点
**新增** `GET /v1/keywords?platform=midjourney`
- 返回该平台相关的关键词列表（从 `mj_style_final.json` 筛选）

**现有** `POST /v1/classify` 已返回 `keywords_found`
- 只需在 Workbench 读取并渲染

### 前端变更

#### 关键词面板
```
优化结果下方新增：
┌─ 关键词注入 (默认折叠) ─────────────────┐
│ [✓] 启用关键词注入                       │
│ [majestic] [royal] [velvet] [golden] ... │
│ 共 12 个词 (点击可复制)                  │
│ [刷新关键词]                             │
└───────────────────────────────────────┘
```

#### 开关逻辑
- 默认 `enabled=true`
- 关闭 → 重新优化，结果不应包含关键词
- 后端 keyword_injector 无条件注入（除非 style=None），前端只做显示

### 数据流
```
POST /v1/optimize → classifier.detect() 返回 categories
                  → keyword_injector.inject() → 注入关键词
                  → 返回结果含 detected_categories.keywords_found
                  
Workbench 接收结果 → 提取 keywords_found → 显示在面板
```

## 不做什么
- ❌ 不支持 UI 增加/删除关键词（仅在 panel 中显示）
- ❌ 不支持复杂关键词管理（不改 yaml 库）
