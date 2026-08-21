# 设计：LLM 输出兼容（推理模型）

## 现状

- `prompt_engine/llm/openai_compat.py:chat()` 每次固定传 `max_tokens=self._max_tokens`（默认 500）、`timeout=self._timeout`（默认 15），只读 `message.content or ""`。
- `prompt_engine_core/llm.py:_request()` 直接 `data["choices"][0]["message"]["content"]`（键缺失 KeyError）。

## 方案

### OpenAICompatProvider

- `__init__`：`self._max_tokens = config.get("max_tokens")`（None 表示省略）；`self._timeout = config.get("timeout", 120)`。
- `chat()`：
  - `create(..., **( {"max_tokens": self._max_tokens} if self._max_tokens else {} ), timeout=self._timeout)`。
  - 读取 `message.content`；若为空且存在 `reasoning_content`（非空），`logger.warning` 输出 finish_reason/reasoning 长度等诊断，仍返回 `""`（不伪造、不把思考当提示词）。
  - 保留 `usage.total_tokens`。

### 共享内核（prompt_engine_core/llm.py）

- `content = data["choices"][0]["message"].get("content")`（安全读取）；其余不动。

### 测试（04-tests/test_llm_reasoning_output_compat.py）

- mock SDK `chat.completions.create`：
  1. 缺省配置 → create 不含 `max_tokens`、timeout=120，content 原样返回（普通模型路径不变）。
  2. 显式 max_tokens=500 → create 带 max_tokens=500（优先级保留）。
  3. content 空 + reasoning_content 有值 → 返回 ""，create 仅 1 次，不伪造。
  4. 共享内核 `.get("content")`：消息无 content 键不抛 KeyError。

## 不做的

- 不从 reasoning_content 提取最终提示词（不可靠，违背 fail-closed）。
- 不在 engine 层重复 PR #67 的重试/回退。
- 不改 video 引擎默认预算。
