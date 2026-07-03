# PM-PRD v0.9.2 — 图片预览修复

## 概述

Pollinations AI 现在要求付费（402 Payment Required），原"免费无限"假设失效。新增 4 个免费替代方案供用户选择。

## 背景

用户报告："选择默认的 Pollinations AI 生成预览失败，图片为空"。
- 根因：Pollinations 改付费政策（自 2026-06-13 起）
- 影响：所有 14 个预设图片模型中只有 Pollinations 是免费的，剩余 13 个需 API Key
- 决策：必须用 1 个替代方案 + 1 个真正可用的免费图源

## 方案对比

| 方案 | 是否免费 | 是否可用 |
|------|---------|---------|
| **Picsum Photos** | ✅ 完全免费 | ✅ 可用（但只能返回随机图片） |
| **Unsplash Source** | ✅ 免费 | ⚠️ 需验证 |
| **Pravatar (随机头像)** | ✅ 免费 | ✅ 可用 |
| **Lorem Picsum + prompt** | ✅ 免费 | ✅ 可用（hash 生成固定图片） |
| **Pollinations** | ❌ 收费 | ❌ 失效 |

**最优方案：**
1. 默认 → **Picsum Photos**（确定性图片 + 免费）
2. 保留 14 个原始模型供按需配置
3. 前端显示图片生成状态（loading/error/empty）

## 功能清单

| 功能 | 等级 | 描述 |
|------|------|------|
| **F1 默认图源切换** | P0 | Picsum Photos 替代 Pollinations |
| **F2 图片加载状态** | P0 | 前端区分 loading/loaded/error |
| **F3 错误处理** | P0 | 加载失败时显示占位图 |
