# ARCH-F13: 反馈闭环 UI

## 目标

将 4 个后端反馈端点暴露到前端，让用户可以赞/踩优化结果并查看反馈统计。

## 设计

### 前端新增

**Workbench 优化结果下方：**
```
赞/踩按钮 → POST /v1/feedback → 更新统计
```

**Settings 新增「反馈统计」卡片：**
```
总反馈数: 47 | 赞: 35 (74%) | 踩: 12 (26%)
最近反馈列表 (10条)
[应用反馈] 按钮 → POST /v1/feedback/apply
```

### 端点映射

| 按钮/UI | 端点 | 参 |
|---------|------|----|
| 赞 | `POST /v1/feedback` | `{entry_type: "positive", optimized_prompt, platform}` |
| 踩 | `POST /v1/feedback` | `{entry_type: "negative", optimized_prompt, platform}` |
| Settings 卡片 | `GET /v1/feedback/stats` | - |
| Settings 列表 | `GET /v1/feedback/recent?limit=10` | - |
| Settings 按钮 | `POST /v1/feedback/apply` | - |

### 关键决策
- 赞/踩数据直接走已有 feedback endpoints
- Settings 反馈统计卡片复用现有的 API
- 提交反馈后即时显示 Toast 确认