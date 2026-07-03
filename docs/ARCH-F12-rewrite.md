# ARCH-F12: 扩写 UI

## 目标
Workbench 增加扩写区，输入简写 prompt → 一键扩写到 300 词

## 设计

### 端点
**现有** `POST /v1/rewrite`
```json
{"prompt": "a cat", "platform": "midjourney", "max_length": 300}
```
```json
{"optimized_prompt": "A majestic feline sitting gracefully on...", "duration_ms": 1234}
```

### 前端变更

#### 扩写区
Workbench 现有「优化 / 分类 / 评估」按钮右侧新增：

```
[扩写:____________] [扩写]  ← 新增
                       ↓
[结果: A majestic feline...]
[耗时: 1234ms] [📋 复制]
```

#### 逻辑
- 输入简写（`"a cat"`, `"sunset"` 等）
- 点击「扩写」
- 调用 `/v1/rewrite`
- 显示扩写结果

### 复用
- `copyText()` 函数已存在（v0.10.0 批量优化时加的）
- `optimizeResult` 渲染方案已存在

### 关键决策
| 决策 | 原因 |
|------|------|
| **独立输入框** | 与原 textarea 独立（用户可以优化后再扩写） |
| **max_length=300** | 扩写的目的是扩展，不是截断 |
| **复用已有 copyText** | 减少代码量 |