# Review: fix-llm-empty-reasoning (prompt-engine)

## 问题根因
用户视频任务在「提示词优化」阶段失败，真实错误为「LLM 返回了空内容或仅包含推理内容，未生成有效优化词」。根因在 prompt-engine：推理模型（如 DeepSeek）只输出思考块、不给最终提示词时，`strip_reasoning_blocks` 剥离后内容为空，优化候选循环立即 `raise RuntimeError`，导致整个请求（以及调用方流水线）失败。Multi-Publish 已做调用方兜底（PR #1069）；本次补齐引擎层，保证作为独立引擎被其它项目调用时同样稳定。

## 修复
- `optimizer.py` 候选循环：剥离推理块后为空 → 有界重试（最多 3 次）；仍为空 → 回退原始 prompt 作为候选并继续，不再抛错。
- 后处理结果为空：同样回退原始 prompt 并继续。
- 回归测试：`test_optimizer_empty_reasoning_retry.py` 3 例（回退原文 / 重试取有效 / 正常直出）。
- 文档：`docs/PRD.md` 增 §14 独立调用契约；CHANGELOG 增条目。

## 验证
- 新增 3 例 passed；`test_optimizer + test_video_optimize` 失败集与基线一致（9 个既有 BYOK mock 环境问题，无新增回归）。
- `python -m py_compile prompt_engine/optimizer.py` 通过。

## 审查结论
- Critical: 无
- Warning: 环境存在 prompt-engine editable 安装指向主仓库，04-tests 用 conftest 引导优先解析当前源码；建议后续统一测试基座。
- Info: 本变更在隔离 worktree 完成，共享主目录零写。
