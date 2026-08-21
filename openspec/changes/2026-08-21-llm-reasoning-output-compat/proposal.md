# OpenAI 兼容 provider 输出兼容（推理模型）

## Why

Multi-Publish 默认 LLM（`opencode-go` / `mimo-v2.5`，经 `openai_compat`）在真实 `/v1/optimize` 中稳定返回 `HTTP 502: LLM 返回了空内容或仅包含推理内容`，最终图片提示词回退原文。根因在 provider 层：`OpenAICompatProvider` 把输出预算锁死为 `max_tokens=500`、超时 15s。推理模型先思考后输出，500 token 预算常被思考耗尽导致 `message.content` 为空；慢响应（27~53s）也会被 15s 超时掐断。桌面端同一网关的成功调用未带 500 上限（且耗时长达 27~53s），证明网关可正常返回内容。
现有 `optimizer.py`（PR #67）已实现「重试 3 次后回退原文」，不解决输出为空，只让整线不致失败；本 change 从 provider 层让推理模型真正能产出内容。

## What Changes

- **输出预算**：`OpenAICompatProvider` 未显式配置 `max_tokens` 时不再传 500 上限，交由网关默认（与桌面端 OpenAI 兼容适配器一致）；显式配置仍覆盖。
- **超时**：默认 `timeout` 15s → 120s（兼容慢推理响应），显式配置仍覆盖。
- **诊断**：响应为「content 空 + reasoning_content 非空」时记录结构化 warning（含 finish_reason、reasoning 长度），不把思考内容当提示词（保持 fail-closed）。
- **共享内核安全读取**：`prompt_engine_core/llm.py` 用 `.get("content")` 读取，避免部分网关缺 content 键时 KeyError；不改其动态 max_tokens 预算。

## Impact

- 文件：`prompt_engine/llm/openai_compat.py`、`prompt_engine_core/llm.py`、新增 `04-tests/test_llm_reasoning_output_compat.py`、`openspec/specs/llm-provider-output-compat/spec.md`、`CHANGELOG.md`、`docs/PRD.md`、`.quality-gates.md`、CCG task。
- 测试：provider 层新增回归（普通 content 路径不变、max_tokens 缺省省略、timeout 默认 120、纯推理不伪造 + 日志诊断）+ 既有 pytest 全量。
- 兼容性：普通模型有 content 时行为不变；仅当 content 为空时才增加诊断；显式 max_tokens/timeout 配置优先级不变。
