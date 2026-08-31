# prompt-engine — 开发规范

> 语言: Python  |  文件数: ~316  |  生成: /init-deep

## 项目概述

prompt-engine: prompt-engine

## 源目录结构

- `prompt_engine/` — 主源码目录
  - `api/`
  - `data/`
  - `knowledge/`
  - `llm/`
  - `prompts_db/`
  - `services/`
  - `strategies/`
  - `templates/`

## 硬约束（来自 .clinerules）

- __init__.py 使用 __getattr__ 惰性导入 Optimizer/Classifier，避免启动时 LLM 连接
- 三级分类流水线顺序不可更改：keyword_match → vector_rag → llm_classify
- 测试必须全部 mock 隔离，不依赖真实 API Key
- 25 个 StyleCategory 枚举在 models.py，不新增不删除
- 权重系统使用 keyword_weights.json 持久化，_get_weights() 惰性加载
- 所有 OpenAI 客户端必须显式注入有界 httpx 连接池（http_client=httpx.Client(limits=...))，禁止默认无限 keep-alive 连接池，防止透明代理中断导致 CLOSE_WAIT 泄漏（详见 references/architecture.md）

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
- 当前: `prompt-engine/`
- 下游: `Story2Video/` — 数据去向

## 详细规范

本文档只包含开发流程框架。详细规范已拆分到 `references/` 子目录：

- **[references/architecture.md](references/architecture.md)** — 硬约束与编码规范

---

## 质量节拍强制执行

本仓库已启用质量节拍（quality-rhythm）门禁系统。每次新任务自动执行：
1. 判断变更类型（14种全覆盖）
2. 评估变更规模
3. 路由到对应 Phase
4. 用户确认后开始

**视觉测试强制：** UI 文件变更时自动提示视觉回归测试。

## 强制工具路由（Iron Rules）

以下规则在 fastctx 引导块之上提供**不可协商的强制执行**。任何违反此规则的操作必须回退重做。

### 文件操作强制路由

| 操作类型 | 必须使用 | 严禁使用 |
|---------|---------|---------|
| 文本搜索 | mcp__fastctx__grep | 禁止 exec_command("rg ...")、exec_command("grep ...")、exec_command("findstr ...")、exec_command("Select-String ...") |
| 文件读取 | mcp__fastctx__read | 禁止 exec_command("cat ...")、exec_command("Get-Content ...")、exec_command("type ...") |
| 文件列表/查找 | mcp__fastctx__glob | 禁止 exec_command("ls ...")、exec_command("dir ...")、exec_command("Get-ChildItem ...") |
| Shell 命令 | mcp__fastctx__run | 禁止 exec_command 直接执行 shell |
| 批量文本替换 | mcp__fastctx__replace | 禁止 exec_command("sed ...")、exec_command("(Get-Content ...) -replace ...") |
| 长时间任务（>2分钟） | mcp__fastctx__run_background | 禁止 exec_command |

### 执行规则

1. 收到用户请求后，Agent 必须先检查操作类型是否命中上表，命中则必须使用对应 FastCtx 工具。
2. apply_patch 仅用于语义级代码修改，不用于机械文本替换。
3. 上表未覆盖的轻量操作（如查询 git status、npm 版本等单行命令）可继续使用 exec_command。


