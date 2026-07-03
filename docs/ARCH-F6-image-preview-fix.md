# ARCH-F6: 图片预览修复（Pollinations 失效）

## 根因

- Pollinations 自 2026-06-13 起 402 Payment Required
- 之前 `https://image.pollinations.ai/prompt/{prompt}` 已不再免费
- 当前 13/14 个模型需要 API Key 才能调用

## 新方案

### 默认图源：Picsum Photos

```
URL: https://picsum.photos/seed/{prompt_hash}/{width}/{height}
返回: 真实的免费图片
特点: 基于 prompt hash 产生确定性图片（同一 prompt 同图）
```

**优点：**
- ✅ 完全免费
- ✅ 真实图片（不是占位图）
- ✅ 响应稳定（已验证 200 OK）
- ✅ 同一 prompt 同一图（hash 确定性）

### 模型清单保持 14 个

| 模型 | 状态 |
|------|------|
| Picsum (默认, 真实免费) | ✅ 可用 |
| Pollinations (标注已失效) | ❌ 显示警告 |
| DALL-E 3/2/GPT-Image-1 | 🔑 需 API Key |
| Flux Pro/Schnell | 🔑 |
| SDXL/SD3.5 | 🔑 |
| 其他 | 🔑 |

### 端点设计

`POST /v1/preview` 保持不变，但：
- 缺省 model = "picsum"（替换 pollinations）
- 缺省返回 picsum URL（真实可用）
- 其他模型保持 placeholder

### 前端修复

- `<img>` 标签增加 `onerror` fallback（占位图）
- 显示模型来源标签（free/key-required）
- 加载中显示 spinner
