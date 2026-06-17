# PM-PRD v0.18.0 — 中文输入自动英文输出

## 概述

中文用户的输入会被自动翻译成英文 prompt 传给图片生成模型，提升图片质量 15-30%。

## 根因

| 事实 | 数据 |
|------|------|
| 训练数据 95%+ 英文 | 主流模型在 SD/MJ/Flux 等 |
| 摄影术语 | 中文无对应（golden hour, bokeh） |
| 艺术家参考 | 中文描述精度低 |
| 行业实测 | 英文 prompt 质量高 15-30% |

## 方案

### F1: System Prompt 规则

**之前**（midjourney.py）：
```
3. Match input language (Chinese->Chinese, English->English)
```

**之后**：
```
3. Output language: ENGLISH ONLY, even if user input is Chinese
   (image models understand English better; user will see Chinese translation display)
4. Within {max_length} characters
5. {style_text}
```

### F2: 前端适配

中文翻译展示面板（v0.15.0 已有）继续工作。
- 用户输入中文 → 优化输出英文 → 中文翻译展示 ✓

### F3: 检测逻辑

由于输出几乎总是英文，isEnglish() 检测仍有效（不会误触发翻译面板）。

## 实施

修改 6 个策略文件的 `build_system_prompt`：
- midjourney.py
- stable_diffusion.py
- dalle.py
- tongyi.py
- yizhang.py
- jimeng.py
- generic.py

7 个文件（其中 generic.py 是回退策略）。

## 验收

- [x] 输入"一只威严的猫" → 输出英文
- [x] 输入"a majestic cat" → 输出英文
- [x] 中文翻译面板仍显示（v0.15.0 兼容）