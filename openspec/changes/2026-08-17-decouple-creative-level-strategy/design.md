# decouple-creative-level-strategy - Design

## Decision

用独立的执行策略表达资源与质量意图，保留 `creative_level` 作为生成强度参数。

| Strategy | Image | Video | LLM bind | Cache |
| --- | --- | --- | --- | --- |
| default | caller LLM at any level | caller LLM | required, fail-closed | normal unless bypassed |
| `template` | deterministic template | rejected (422) | not required | normal |
| `llm` | caller LLM at any level | caller LLM | required, fail-closed | normal unless bypassed |
| `auto` | rejected (422) | rejected (422) | not applicable | not applicable |

## Rationale

项目尚未正式上线，不保留旧 SDK 或旧数据兼容分支。缺省统一走调用方 `llm`，模板必须显式选择；模板固定输出，避免随机标签把重复调用伪装成重新生成。`bypass_cache=true` 表达人工操作要获得一次真实计算，而非复用旧命中。

## Safety and Observability

- REST/MCP 在 LLM 路径缺 `llm` 时返回 422；不读服务端 Key。
- 缓存键包含 caller/provider/model/base_url/API Key 摘要和请求策略。
- 结果返回 `strategy_used`、`key_source`、`model_used`、`caller`、`cache_hit`。
- API Key 摘要仅用于缓存身份隔离，原文不写日志或响应。

## Rollback

调用方不传 `optimization_strategy` 时走 `llm`；传入已删除的 `auto` 直接返回 422。
