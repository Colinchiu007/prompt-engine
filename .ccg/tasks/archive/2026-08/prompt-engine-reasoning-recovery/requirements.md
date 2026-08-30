# 需求

- `content` 为空但 `reasoning_content` 非空时，provider 最多重试两次（共三次调用），逐步追加用户指令和 final-output system 指令，小 `max_tokens` 自动提升到 8192。
- 补充 request / raw response / retry / 最终结果的结构化日志，覆盖模型、消息长度、max_tokens、finish_reason、content/reasoning 长度、延迟、token。
- 图片域 LLM 重试耗尽后使用模板优化兜底，不再直接回原文；视频域保持 fail-closed 回原文。
- 示例配置移除 `openai_compat` 的 `max_tokens: 500`，timeout 对齐 120s。
- Multi-Publish 桌面 PromptBridge HTTP/CLI fallback 超时提至 120s。
