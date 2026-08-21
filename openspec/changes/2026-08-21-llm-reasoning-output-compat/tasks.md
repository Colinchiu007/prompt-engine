# llm-reasoning-output-compat - Tasks

- [ ] OpenAICompatProvider：默认省略 max_tokens（显式配置保留），默认 timeout 120
- [ ] OpenAICompatProvider：纯推理响应（content 空 + reasoning 非空）诊断日志且不伪造
- [ ] prompt_engine_core/llm.py：message.content 安全读取（.get）
- [ ] 新增 provider 层回归测试（普通路径不变/显式预算保留/纯推理诊断/无 content 键不崩）
- [ ] pytest 全量回归 + 语法自检
- [ ] CCG 双模型分析 + 双模型审查
- [ ] CHANGELOG / docs/PRD / OpenSpec 同步
- [ ] commit / push / PR / CI / merge / 归档
