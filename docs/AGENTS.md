# Prompt Engine — AI Agent 开发指南

## 项目概览

Prompt Engine (项目 011) 是一个图片生成提示词优化引擎。Python 包，非 Electron 项目。

## 关键路径

```
prompt_engine/
├── optimizer.py          # 编排器入口
├── classifier.py         # 25 维风格分类器（三级流水线）
├── cache.py              # SQLite + Memory 双级缓存
├── template_engine.py    # Prompt-as-Code 模板引擎
├── keyword_injector.py   # 跨平台关键词注入
├── cli.py                # 命令行工具
├── feedback.py           # 用户反馈存储
├── strategies/           # 7 个平台策略文件
├── api/                  # REST + MCP Server
├── web/                   # Vue 3 Web 看板
├── models.py             # 所有 Pydantic 模型
├── templates/styles.yaml # 风格模板（含 StyleCategory）
├── data/mj_style_final.json  # MJ 关键词数据库
└── agents/skills/prompt-engine/  # Agent Skill (SKILL.md)

tests/
├── test_rag_seed.py      # 506 案例 RAG 种子测试
├── test_prompt_template.py  # Prompt-as-Code 模板测试
├── test_gpt4o_prompts.py  # gpt4o 1050 案例 RAG 种子测试
├── test_dsl_parser.py     # DSL 模板语法解析器测试
├── test_dashboard_api.py  # 看板统计 API 测试(4)
├── test_resources_preview.py  # 资源/预览/模型测试(9)
└── ... (224 总用例)
```

## 重要约定

1. **惰性导入** — `__init__.py` 使用 `__getattr__` 惰性导入 Optimizer/Classifier，避免启动时 LLM 连接
2. **测试隔离** — 224 个测试全部 mock 隔离，无需 API Key
3. **三级分类流水线** — keyword_match → vector_rag → llm_classify，不修改此流程
4. **25 个 StyleCategory** — 枚举在 models.py，已移除 rainbow_of_colors
5. **权重系统** — `keyword_weights.json` 持久化，`_get_weights()` 惰性加载
6. **Agent Skill** — `agents/skills/prompt-engine/SKILL.md`，用 `npm run install:skill` 安装到本地 Agent

## 测试

```bash
pytest tests/ -q        # 250 tests, ~25s
pytest tests/ -x --tb=short  # 失败即停
```

## 版本

当前 v0.19.0，所有 s1-s5 + P0-P4 + F1-F12 + v0.16-v0.19 已完成。
