# ARCH-F2: AI 图片预览

## 目标

Workbench 优化完 prompt 后，用户可一键生成预览图，实时看到优化效果。

## 设计

### 核心思路

不实际调任何付费 API（避免账单 + 避免未配 Key 的 401）。**Pollinations AI 公开 URL 直接可访问**，是首选实现。

### 端点

```
POST /v1/preview
GET  /v1/image-models
```

### POST /v1/preview

#### 请求

```json
{
  "prompt": "a majestic cat",
  "model": "pollinations",  // 可选，默认 pollinations
  "width": 1024,            // 可选
  "height": 1024,           // 可选
  "seed": -1                // 可选，-1 表示随机
}
```

#### 响应（Pollinations）

```json
{
  "url": "https://image.pollinations.ai/prompt/a%20majestic%20cat?width=1024&height=1024&nologo=true",
  "model": "pollinations",
  "width": 1024,
  "height": 1024,
  "prompt": "a majestic cat"
}
```

#### 响应（其他模型）

```json
{
  "url": "",
  "model": "dall-e-3",
  "note": "该模型需配置 API Key，请前往 Settings 页面配置"
}
```

### GET /v1/image-models

返回 14 个预设模型清单，每条包含：

```json
{
  "id": "pollinations",
  "name": "Pollinations AI",
  "provider": "Pollinations",
  "requires_key": false,
  "description": "免费，无需 API Key，调用即用",
  "endpoint": "https://image.pollinations.ai/prompt/{prompt}"
}
```

## 前端集成

Workbench「优化结果」tab 末尾：

```
┌─────────────────────────────────────┐
│ ✨ 优化结果                          │
│                                     │
│ A majestic cat...                   │
│ [midjourney] [耗时 1234ms]          │
│                                     │
│ ── 🖼️ 图片预览 ─────────────────    │
│                                     │
│ [模型下拉▼] [生成预览] [清除]       │
│                                     │
│ ┌──────────────┐                    │
│ │   预览图     │                    │
│ │  pollinations│                    │
│ │  1024×1024   │                    │
│ └──────────────┘                    │
└─────────────────────────────────────┘
```

## 决策

| 选择 | 原因 |
|------|------|
| **Pollinations 作为默认** | 免 API Key、即点即用、URL 直接可访问（`<img src=...>` 即可）|
| **不调付费 API** | 避免未配 Key 的 401 错误影响体验，避免账单风险 |
| **保留其他模型清单** | 用户能在 Settings 看到完整选项，按需配置 Key |
| **URL 由后端构造** | 避免前端暴露 endpoint 结构，方便后续切换实现 |

## 已知限制

- 仅 Pollinations 实际可生成图（其他模型需要 Key 实际接入才能工作）
- 不支持图片返回 base64（避免大文件通过 API）
- 不做图片缓存（浏览器 img 标签会按 URL 重新请求）
