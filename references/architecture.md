# prompt-engine — 硬约束与编码规范

## 硬约束（来自 .clinerules）

- __init__.py 使用 __getattr__ 惰性导入 Optimizer/Classifier，避免启动时 LLM 连接
- 三级分类流水线顺序不可更改：keyword_match → vector_rag → llm_classify
- 测试必须全部 mock 隔离，不依赖真实 API Key
- 25 个 StyleCategory 枚举在 models.py，不新增不删除
- 权重系统使用 keyword_weights.json 持久化，_get_weights() 惰性加载

## PRD 参考

- PRD: `docs/PRD.md` — Prompt Engine — PRD v0.9.3

## 入口文件

- `CLAUDE.md` — 开发指南和命令
- `.clinerules` — 项目特定硬约束
- `docs/PRD.md` — 产品需求文档
- `prompt_engine/` — 源码入口
- `AGENTS.md` — 本文件，AI 行为规范

## 管道位置

- 上游: `smart-sentence-splitter/` — 数据来源
