# decouple-creative-level-strategy - Proposal

## Why

图片优化的 `creative_level` 被历史兼容规则同时用作“创意强度”和“是否调用 LLM”的开关。调用方无法表达“低等级但必须使用用户模型”或“高等级但需要确定性模板”；历史记录手动重生成还可能命中缓存，造成“已重新生成”的假象。

## What Changes

- 在 `OptimizeRequest` 中支持 `optimization_strategy=template|llm`，缺省为 `llm`。
- 删除 `auto` 策略；传入 `auto` 返回 HTTP 422。
- `creative_level` 只控制创意/细节强度，不参与执行路径选择。
- `template` 仅限图片，`llm` 无视等级强制使用调用方 BYOK 模型。
- 增加 `bypass_cache` / `cache_hit` 可观测契约；手动重生成不读也不写缓存。
- 保持 optimize 路径只使用请求 `llm`，不回退 `config.yaml` 的 LLM Key。

## Impact

- 修改图片优化请求/结果、REST/MCP、缓存键和模板渲染语义。
- Multi-Publish 历史图片优化显式传 `llm + bypass_cache`。
- 项目尚未正式上线，不保留旧策略或旧缓存格式兼容。
