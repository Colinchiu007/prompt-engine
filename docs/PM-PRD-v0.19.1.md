# PM-PRD v0.19.1 — PROJECT-012 上下文注入

## 概述

PROJECT-012（语义分句引擎）对剧本/故事分句后，每句可附带上下文（场景、角色、故事梗概）。PROJECT-011 需要接收并消费这些上下文，确保 LLM 在生成图片 prompt 时保持角色一致性。

## 背景

| 问题 | 现象 | 影响 |
|------|------|------|
| 多张图角色不一致 | 同一角色（如「小明」）在不同分句中生成不同外貌 | 故事连贯性差，用户需手动修正 |
| 手动拼 context 到 prompt | 用户需在 prompt 中手动描述角色/场景 | 操作繁琐，易遗漏 |
| 无标准接口契约 | PROJECT-012 和 PROJECT-011 各自独立，无法对接 | 两条产品线隔离 |

## 需求

### F6: Context 字段定义

`OptimizeRequest` 增加 `context: Optional[dict]`：

| 子字段 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `setting` | str | 否 | 当前场景描述 |
| `character` | dict | 否 | 当前主角：`{"name": "Tom"}` |
| `character_list` | list[dict] | 否 | 全部角色列表 |
| `synopsis` | str | 否 | 故事梗概（截断 200 字） |

### F7: 角色一致性注入

`optimize()` 在构建 system prompt 后、调用 LLM 前，将 context 注入为角色一致性指令：

- 双语指令（英文 + 中文，兼顾 LLM 理解和中文用户阅读）
- 指令要求「相同名字的角色在所有图片中保持同一身份」
- 注入位置：build_system_prompt() 之后，few-shot 检索之前

### 不破坏的范围

- 不传 context 时行为完全不变（默认 None，不注入任何内容）
- 所有现有 API 签名不变
- 所有现有测试无需修改
- 7 个平台策略文件无需修改（注入由 optimizer.py 统一处理）

## 验收标准

- [ ] `OptimizeRequest(context=None)` 向后兼容
- [ ] `OptimizeRequest(context={...})` 正确存储
- [ ] context 非空时 system prompt 含「Character consistency」段落
- [ ] context 为空 dict `{}` 不崩溃
- [ ] context 缺部分字段（只有 character）不崩溃
- [ ] context 内容正确反映在 system prompt 中
- [ ] batch 请求中每条可带各自 context
- [ ] AGENTS.md / INTEGRATION.md 更新（已同步）
- [ ] pyproject.toml 版本号更新（0.19.0 → 0.19.1）

## 数据流

```
PROJECT-012                       PROJECT-011
  │                                   │
  │  SmartSentenceSplitter.split()    │
  │  → scenes[] with context          │
  │                                   │
  │  PromptEngineExporter             │
  │  → batch: [{prompt, context}]     │
  │                                   │
  │  POST /v1/optimize/batch          │
  │─────────────────────────────────>│
  │                                   │
  │                            OptimizeRequest.context  ✓
  │                                   │
  │                            optimize()
  │                              ├─ build_system_prompt()
  │                              ├─ inject context → █角色一致性█
  │                              ├─ _retrieve_few_shot()
  │                              ├─ _call_llm()
  │                              └─ post_process()
  │                                   │
  │  {optimized_prompts[]}            │
  │<─────────────────────────────────│
```

## 变更清单

| 文件 | 变更 | 行数 |
|------|------|------|
| `prompt_engine/models.py` | OptimizeRequest 加 context 字段 | +1 |
| `prompt_engine/optimizer.py` | optimize() 注入 context → system prompt | +18 |
| `docs/AGENTS.md` | 新增 v0.19.1 发行说明 | +5 |
| `docs/INTEGRATION.md` | 新增 PROJECT-012 集成章节 | +66 |
| `pyproject.toml` | 0.19.0 → 0.19.1 | +1 |
