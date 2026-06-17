# ARCH-F9: 批量优化 UI

## 目标

Workbench 支持「一次提交多个 prompt」批量优化，降低重复点击。

## 设计

### UI 变更

新增「批量模式」切换按钮：
- **单条模式** (默认)：textarea + 「优化 Prompt」按钮
- **批量模式**：textarea (多行) + 「批量优化」按钮 + 进度条 + 结果列表

### 交互流程

```
[Workbench]
  [单条] | [批量]  ← 切换
  ↓ 批量模式
  [textarea: 多行 prompt]
  [平台: midjourney ▼]  [批量优化]
  ↓ 进度
  [进度条: 3/10 (正在处理第 4 个)]
  ↓ 完成后
  [结果列表]
    [1] a majestic cat → A majestic feline... (1234ms)
    [2] cyberpunk city → A neon-lit metropolis... (1456ms)
    ...
  每条:
    [📋 复制] [💾 下载] [🖼️ 生成预览]
```

### 端点

复用现有：
```
POST /v1/optimize/batch
{
  "requests": [
    {"prompt": "a cat", "platform": "midjourney"},
    {"prompt": "cyberpunk city", "platform": "midjourney"}
  ]
}
```

### 关键决策

| 决策 | 原因 |
|------|------|
| **每行一个 prompt** | 简单、复制粘贴友好 |
| **最大 10 个/批** | LLM 配额保护（10 个 OpenAI 调用 ≈ $0.05） |
| **同平台批量** | 简化 UI（一个平台 → 多个 prompt） |
| **结果逐条显示** | 部分失败不影响其他 |
| **可展开/折叠** | 长结果列表节省屏幕空间 |

### 前端实现

```js
// Workbench 加 batchMode 状态
const batchMode = ref(false);

// 切换 UI
const inputRows = computed(() => 
  input.value.split('\n').filter(l => l.trim())
);

// 批量调用
async function optimizeBatch() {
  const prompts = inputRows.value.slice(0, 10);
  batchProgress.value = { done: 0, total: prompts.length };
  
  for (let i = 0; i < prompts.length; i++) {
    try {
      const d = await api.post('/v1/optimize', {
        prompt: prompts[i], platform: platform.value
      });
      batchResults.value[i] = { prompt: prompts[i], result: d, error: null };
    } catch (e) {
      batchResults.value[i] = { prompt: prompts[i], result: null, error: e };
    }
    batchProgress.value.done++;
  }
}
```

## 验收

- ✅ 输入 3 行 → 输出 3 个结果
- ✅ 中间一条失败，其他 2 条仍正常
- ✅ 进度条实时更新
- ✅ 每条结果可独立复制/下载/预览
