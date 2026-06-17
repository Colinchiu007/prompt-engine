# PM-PRD v0.16.1 — 输入引导面板

## 概述

输入太短（"好吧"等）时，当前只返回 400 错误 + 一行提示文字。用户仍然不知道怎么填。新增引导面板，提供可点击的主题和示例。

## 方案

### 后端改动

无。400 错误 msg 已够。

### 前端改动

Workbench 的 `optimize()` 函数捕获 400 错误时，不显示 error banner，改为显示**引导面板**：

```
┌─ 描述太简短了（2 字）─────────────┐
│                                    │
│ 💡 试试更详细地描述你想生成的画面    │
│                                    │
│ 选择主题：                          │
│ [🏞️ 风景] [🐱 动物] [🧑 人物]      │
│ [🌃 科幻] [🎨 抽象] [🧙‍♂️ 奇幻]    │
│                                    │
│ 或一键使用示例：                    │
│ 📝 一只威严的猫端坐在天鹅绒宝座上    │
│ 📝 赛博朋克城市夜景霓虹灯光         │
│ 📝 梦幻森林中的魔法光斑             │
│                                    │
│ [× 关闭]                           │
└────────────────────────────────────┘
```

### 主题 → 示例映射

| 主题 | 示例 |
|------|------|
| 🏞️ 风景 | "sunset over mountain lake with mist" |
| 🐱 动物 | "a majestic cat sitting on a velvet throne" |
| 🧑 人物 | "portrait of a warrior queen with golden armor" |
| 🌃 科幻 | "cyberpunk city at night with neon lights" |
| 🎨 抽象 | "abstract fluid art with vibrant colors" |
| 🧙‍♂️ 奇幻 | "enchanted forest with glowing mushrooms" |

## 验收

- [x] 输入"好吧" → 显示引导面板（非简单 error）
- [x] 点击主题按钮 → 填充对应示例
- [x] 点击示例文本 → 自动填入输入框
- [x] 点击关闭 → 面板消失
- [x] 正常优化错误（非 400）仍显示 error banner