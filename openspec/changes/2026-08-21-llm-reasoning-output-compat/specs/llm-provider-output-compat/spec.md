# llm-provider-output-compat Specification Delta

## ADDED Requirements

### Requirement: OpenAI 兼容 provider 推理模型输出兼容

`OpenAICompatProvider` 在调用 `chat.completions.create` 时：未显式配置 `max_tokens` MUST 省略该字段（交由网关默认预算），显式配置 MUST 原样透传；默认超时 MUST 为 120s（显式配置覆盖）。普通模型（`message.content` 非空）响应 MUST 原样返回，行为不因本项变化。

#### Scenario: 慢推理模型正常出内容
- **WHEN** 未配置 max_tokens 且网关按默认预算返回 `content` 非空
- **THEN** 返回该 content，请求体不含 500 上限，超时预算 120s

#### Scenario: 显式预算仍生效
- **WHEN** provider 配置 max_tokens=500
- **THEN** create 请求带 max_tokens=500

### Requirement: 纯推理响应诊断且不伪造

响应 `message.content` 为空且 `reasoning_content` 非空时，provider MUST 记录含 `finish_reason` 与 reasoning 长度的结构化 warning，返回空文本（交由上层既有回退原文逻辑），MUST NOT 把思考内容当作提示词返回。

#### Scenario: content 空 + reasoning 非空
- **WHEN** message.content 为空、reasoning_content 有推理文本
- **THEN** 返回 "" 并告警，不拼接/伪造提示词

### Requirement: 共享内核消息读取安全

`prompt_engine_core/llm.py` 读取首个 choice 的 `message.content` MUST 使用 `.get("content")`，网关缺失 content 键时不抛 KeyError。

#### Scenario: 无 content 键
- **WHEN** 响应 message 缺少 content 键
- **THEN** 返回空文本而非 KeyError
