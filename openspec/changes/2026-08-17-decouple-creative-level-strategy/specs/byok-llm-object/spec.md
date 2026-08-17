# byok-llm-object Specification Delta

## MODIFIED Requirements

### Requirement: 调用方 LLM 绑定（BYOK）

优化请求缺省或显式 `optimization_strategy=llm` 时 SHALL 使用调用方 `llm` 绑定。`optimization_strategy=template` 仅限图片并免 LLM。`auto` 已删除，传入 MUST 返回 HTTP 422。LLM 绑定缺失或非法 MUST 返回 HTTP 422，且不得回退服务端 Key；`creative_level` 只控制创意/细节强度。

#### Scenario: 显式策略覆盖等级
- **WHEN** 图片请求 level=1 + strategy=llm，或 level=10 + strategy=template
- **THEN** 分别使用调用方 LLM 或模板，等级不覆盖策略

### Requirement: 缓存键并入 provider 身份

缓存键 MUST 隔离调用方、provider、model、base_url、API Key 摘要及执行策略；`bypass_cache=true` MUST 跳过读写，结果返回 `cache_hit=false`。

#### Scenario: 手动重生成绕过缓存
- **WHEN** LLM 请求带 bypass_cache=true
- **THEN** 真实执行调用方模型，不读写优化缓存
