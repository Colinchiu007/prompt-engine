# llm-reasoning-output-compat - Tasks

- [x] OpenAICompatProvider：默认省略 max_tokens（显式配置保留），默认 timeout 120
- [x] OpenAICompatProvider：纯推理响应（content 空 + reasoning 非空）诊断日志且不伪造
- [x] prompt_engine_core/llm.py：message.content 安全读取（.get）
- [x] 新增 provider 层回归测试（普通路径不变/显式预算保留/纯推理诊断/无 content 键不崩）
- [x] pytest 相关模块回归（54 passed）+ 语法自检（compileall / diff --check）
- [x] CCG 双模型分析 + 审查（外部 wrapper 本环境不可用，按机制硬化降级为主代理直审）
- [x] CHANGELOG / OpenSpec / .quality-gates 同步
- [x] commit / push / PR(#68) / CI / squash 合并 / 归档
