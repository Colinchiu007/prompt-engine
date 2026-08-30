# prompt-engine — 硬约束与编码规范

## 硬约束（来自 .clinerules）

- __init__.py 使用 __getattr__ 惰性导入 Optimizer/Classifier，避免启动时 LLM 连接
- 三级分类流水线顺序不可更改：keyword_match → vector_rag → llm_classify
- 测试必须全部 mock 隔离，不依赖真实 API Key
- 25 个 StyleCategory 枚举在 models.py，不新增不删除
- 权重系统使用 keyword_weights.json 持久化，_get_weights() 惰性加载

## LLM 客户端连接池硬约束（QM-5 CLOSE_WAIT 泄漏复盘）

- **所有 `OpenAI(...)` 客户端必须显式注入有界 httpx 连接池**（`http_client=httpx.Client(limits=httpx.Limits(...))`），禁止依赖默认无限 keep-alive 连接池。
- 理由：透明代理（如 OpenWrt OpenClash）中断 keep-alive 长连接时，默认连接池不及时 close() 释放 socket，导致 CLOSE_WAIT 泄漏堆积。
- 连接池限制参考：`max_connections=5`、`max_keepalive_connections=2`、`keepalive_expiry=30.0`（见 `prompt_engine/llm/openai_compat.py` 的 `_CONNECTION_POOL_LIMITS`）。
- 新增/修改任何 LLM provider（`prompt_engine/llm/*.py`）时，必须同步配置有界连接池，并补充回归测试断言客户端使用有界连接池（模式见 `tests/test_llm_connection_pool.py`）。

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
