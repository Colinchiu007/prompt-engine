# ARCH-F2: 多模型供应商扩展方案

## 目标

借鉴 prompt-optimizer 的 20+ 供应商适配器架构，扩展 prompt-engine 的 LLM 供应商层，新增 DeepSeek、Gemini、SiliconFlow。

## 当前状态

```
llm/
├── base.py             # BaseLLMProvider (抽象)
├── openai_compat.py    # OpenAI 兼容 (OpenAI, OpenRouter, 等)
├── xfyun.py            # 讯飞星火
```

## 新架构

```
llm/
├── base.py
├── openai_compat.py    # 不变
├── xfyun.py            # 不变
├── deepseek.py         # 新增 — DeepSeek API (openai-compatible)
├── gemini.py           # 新增 — Google Gemini API
├── siliconflow.py      # 新增 — SiliconFlow API (openai-compatible)
```

## 实现方式

DeepSeek 和 SiliconFlow 都是 OpenAI 兼容 API，可直接用 `openai_compat.py` 配置。
Gemini 需要独立实现（不同 API 格式）。

实际实现：
- DeepSeek → 无需新文件，在 config.yaml 添加 `openai_compat` 配置
- SiliconFlow → 同上
- Gemini → 需要新 provider，使用 `google-genai` SDK

## 测试

- 测试配置加载
- 测试 Gemini provider 的 chat 实现
