# Prompt Engine — AI Agent 开发指南

## 项目概览

Prompt Engine (项目 011) 是一个图片生成提示词优化引擎。Python 包，非 Electron 项目。

## 关键路径

```
prompt_engine/
├── optimizer.py          # 编排器入口
├── classifier.py         # 25 维风格分类器（三级流水线）
├── keyword_injector.py   # 跨平台关键词注入
├── cli.py                # 命令行工具
├── feedback.py           # 用户反馈存储
├── strategies/           # 7 个平台策略文件
├── api/                  # REST + MCP Server
├── models.py             # 所有 Pydantic 模型
├── templates/styles.yaml # 风格模板（含 StyleCategory）
└── data/mj_style_final.json  # MJ 关键词数据库
```

## 重要约定

1. **惰性导入** — `__init__.py` 使用 `__getattr__` 惰性导入 Optimizer/Classifier，避免启动时 LLM 连接
2. **测试隔离** — 127 个测试全部 mock 隔离，无需 API Key
3. **三级分类流水线** — keyword_match → vector_rag → llm_classify，不修改此流程
4. **25 个 StyleCategory** — 枚举在 models.py，已移除 rainbow_of_colors
5. **权重系统** — `keyword_weights.json` 持久化，`_get_weights()` 惰性加载

## 测试

```bash
pytest tests/ -q        # 127 tests, ~25s
pytest tests/ -x --tb=short  # 失败即停
```

## 版本

当前 v0.5.0，所有 s1-s5 + P0-P4 已完成。
