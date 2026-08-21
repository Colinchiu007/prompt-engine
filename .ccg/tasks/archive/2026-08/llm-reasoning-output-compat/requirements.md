# 需求：LLM 输出兼容（推理模型）

## 现象

Multi-Publish 桌面默认 LLM 为 `opencode-go`（base_url=`https://opencode.ai/zen/go/v1`，model=`mimo-v2.5`，provider 映射到引擎 `openai_compat`）。真实流水线中 `/v1/optimize` 返回：

```
HTTP 502: LLM调用失败: LLM 返回了空内容或仅包含推理内容，未生成有效优化词
```

原因：`prompt_engine/llm/openai_compat.py` 的 `OpenAICompatProvider`：
- `max_tokens` 硬编码默认 `500`，对「先思考后输出」的推理模型，思考块即可耗尽预算，`message.content` 为空；
- `timeout` 默认 `15s`，而同一网关在桌面端成功调用的耗时 27~53s，慢响应会在客户端被掐断。

对照组：桌面端 `OpenAIAdapter.chatCompletion()` 仅在调用方显式传 `max_tokens` 时设置该字段；成功调用 `opencode-go`/`mimo-v2.5` 时未带 500 上限且能正常返回 `content`。证明网关本身能返回内容，差异在请求参数与超时。

## 目标

1. `OpenAICompatProvider` 默认不再把输出预算锁死在 500：
   - 未显式配置 `max_tokens` 时交由网关默认（与桌面端一致）；
   - 显式配置仍可覆盖（不影响普通模型现行行为）。
2. 默认 `timeout` 提高到慢推理模型的合理范围（120s），显式配置可覆盖。
3. 对「content 为空 + reasoning_content 非空」的纯推理响应做清晰诊断日志，且不把思考内容当提示词（保持 fail-closed，由上层 optimizer/multi-publish 既有回退原文逻辑兜底）。
4. 普通模型路径零行为变化：有 content 的响应原样返回，不受上述改动影响。

## 约束

- 改动只落在 `prompt_engine/llm/openai_compat.py`（当前失败层）；共享内核 `prompt_engine_core/llm.py` 仅做安全读取加固（.get("content")），不改默认预算。
- `optimizer.py` 已有 PR #67 的「重试 3 次后回退原文」，不重复实现重试/回退逻辑。
- 测试全部 mock 隔离，不依赖真实 API Key；不大改既有 provider 契约测试。
- 用户可见文案不动（无 locale 面）。
