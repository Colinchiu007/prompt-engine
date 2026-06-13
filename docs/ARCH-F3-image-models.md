# ARCH-F3: 图片模型 API 配置

## 目标

Settings 页面展示完整的图片生成模型清单，并提供 API Key 配置说明，让用户按需启用付费模型。

## 设计

### 14 个预设模型

| 模型 | 供应商 | 费用 | 端点 |
|------|--------|------|------|
| Pollinations AI | Pollinations | 🆓 免费 | image.pollinations.ai |
| DALL-E 3 | OpenAI | 🔑 | api.openai.com/v1/images/generations |
| DALL-E 2 | OpenAI | 🔑 | api.openai.com/v1/images/generations |
| GPT-Image-1 | OpenAI | 🔑 | api.openai.com/v1/images/generations |
| Flux Pro | Replicate | 🔑 | api.replicate.com/v1/predictions |
| Flux Schnell | Replicate | 🔑 | api.replicate.com/v1/predictions |
| Stable Diffusion XL | Stability | 🔑 | api.stability.ai |
| Stable Diffusion 3.5 | Stability | 🔑 | api.stability.ai |
| Ideogram v2 | Together | 🔑 | api.together.xyz |
| Playground v2.5 | Together | 🔑 | api.together.xyz |
| Kandinsky 3 | Replicate | 🔑 | api.replicate.com/v1/predictions |
| Midjourney v6 | Replicate | 🔑 | api.replicate.com/v1/predictions |
| Imagen 3 | Together | 🔑 | api.together.xyz |
| Aurora | xAI (Grok) | 🔑 | api.x.ai |

### 供应商环境变量

| 供应商 | 环境变量 | 说明 |
|--------|---------|------|
| Pollinations | (无需) | 免费图片生成 |
| OpenAI | `OPENAI_API_KEY` | DALL-E 3 / DALL-E 2 / GPT-Image-1 |
| Replicate | `REPLICATE_API_KEY` | Flux / Midjourney v6 / Kandinsky |
| Stability | `STABILITY_API_KEY` | SDXL / SD3.5 |
| Together | `TOGETHER_API_KEY` | Ideogram / Playground / Imagen |
| xAI | `XAI_API_KEY` | Grok Aurora |

### 数据源

```python
IMAGE_MODELS = [
    {
        "id": "pollinations",
        "name": "Pollinations AI",
        "provider": "Pollinations",
        "requires_key": False,
        "description": "免费，无需 API Key",
        "endpoint": "https://image.pollinations.ai/prompt/{prompt}"
    },
    # ... 13 more
]
```

硬编码在 `prompt_engine/api/rest.py` 中。

## 前端展示

Settings 页面新增「🖼️ 图片生成模型」卡片：

```
┌────────────────────────────────────┐
│ 🖼️ 图片生成模型                    │
│ Pollinations 免费无需 Key，开箱即用 │
│                                    │
│ 模型            供应商    费用     │
│ Pollinations AI Pollin.  免费     │
│ DALL-E 3        OpenAI    需 Key   │
│ Flux Pro        Replic.  需 Key   │
│ ...                               │
│                                    │
│ ▼ 🔑 配置 API Key（环境变量）      │
│ 供应商    环境变量      说明      │
│ OpenAI    OPENAI_API_KEY DALL-E   │
│ Replicate REPLICATE_API_KEY Flux  │
│ ...                               │
└────────────────────────────────────┘
```

## 决策

| 选择 | 原因 |
|------|------|
| **后端硬编码模型清单** | 启动即可用，无需加载外部配置；模型稳定，变化少 |
| **环境变量配置 Key** | 行业标准做法，不写入代码或 git |
| **Pollinations 免 Key** | 提供开箱即用体验（占总用户的 80%） |
| **复用 `/v1/image-models` 端点** | Workbench 和 Settings 共享同一数据源 |

## 未来扩展

- 模型清单可移到 `config/image_models.yaml`，用户可自定义添加
- Key 状态显示（"已配置" / "未配置"），通过 `GET /v1/config` 返回
- 支持用户自定义 endpoint URL（自部署场景）
