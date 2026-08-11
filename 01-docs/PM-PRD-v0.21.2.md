# PM-PRD v0.21.2 — 提示词优化上下文增强

## 概述

提示词优化引擎（prompt-engine）的 optimize() 接口在接收外部传入的 context 时，已有 setting/character/synopsis 等角色一致性注入能力（v0.19.1）。但在 Story2Video 等图片轮播场景中，消费端需要传递更丰富的**文案意图**（narrative_intent）、**场景类型**（scene_type）和**完整文案摘要**（full_text），当前策略层（generic.py）对这些键缺少感知，导致优化后的提示词与原文案语义脱节。

## 背景

| 问题 | 现象 | 影响 |
|------|------|------|
| 优化后提示词与原文案脱节 | 唐代文案场景「一个老妇人在做饭」-> 优化为「Western elderly woman cooking in modern kitchen」 | 生成图片与文案不贴合 |
| 缺少文案意图传递 | consumer 传 
arrative_intent=historical_essay，但 LLM prompt 无此信息 | LLM 按通用风格优化，忽略文案意图 |
| 缺少场景类型分类 | consumer 传 scene_type=cooking，但 LLM 无烹饪/历史/战争等场景感知 | 场景道具、光影、构图泛化 |
| max_tokens 过短 | 默认 300 tokens，复杂场景优化被截断 | 优化结果不完整 |

## 需求

### F1: 文案意图理解注入（Narrative Understanding）

generic.py 策略新增系统提示词指令段落，要求 LLM 在优化前先理解文案意图。注入条件：context.narrative_intent 非空时，将 
arrative_intent + ull_text 摘要注入 system prompt。

### F2: 场景类型分类指令（Scene Type Classification）

在 generic.py 的 system prompt 中新增场景类型感知指令。注入条件：context.scene_type 非空时注入。

### F3: 完整文案摘要注入（Full Text Context）

当 context.full_text 非空时，在 system prompt 中注入文案摘要（截断至 500 字），让 LLM 在优化单场景提示词时拥有全文视野。

### F4: max_tokens 默认值提升

models.py 中 OptimizeRequest.max_tokens 默认值从 300 -> 500，避免复杂场景优化被截断。

## 不破坏的范围

- context 为 None 或空 dict 时行为完全不变
- 所有现有 API 签名不变
- 
arrative_intent/scene_type/ull_text 为可选键，未传时不注入
- 现有测试无需修改（仅更新断言的 max_tokens 默认值）

## 验收标准

- [ ] context.narrative_intent 非空时，system prompt 含 Narrative Understanding 段落
- [ ] context.scene_type 非空时，system prompt 含 Scene Type Classification 指令
- [ ] context.full_text 非空时，system prompt 含完整文案上下文块
- [ ] context=None 时行为不变（向后兼容）
- [ ] max_tokens 默认值为 500
- [ ] 全部 20/20 测试通过
- [ ] CHANGELOG 同步更新

## 变更清单

| 文件 | 变更 | 行数 |
|------|------|------|
| prompt_engine/models.py | max_tokens 默认值 300->500 | +1/-1 |
| prompt_engine/prompt_builder.py | 重构 uild_context_section，支持 narrative_intent/scene_type/full_text 注入 | +129/-92 |
| prompt_engine/strategies/generic.py | 新增 Narrative Understanding + Scene Type Classification 系统提示词 | +29 |
| 	ests/test_v017_speed.py | 断言更新（max_tokens 默认值） | +3/-3 |

## 关联

- 上游消费方：Multi-Publish PR #525 — 场景上下文增强中间层
- 历史 PRD：v0.19.1（上下文注入基础）、v0.19.0（缓存持久化）
