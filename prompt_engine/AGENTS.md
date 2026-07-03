# prompt-engine/prompt_engine — 源码上下文

> 源码目录 `prompt_engine/`. 本文件在 AI 操作该目录代码时自动加载。

## 目录结构

### Python 模块

- `__init__.py`
- `cache.py`
- `classifier.py`
- `cli.py`
- `config.py`
- `disturb.py`
- `dsl_parser.py`
- `evaluator.py`
- `feedback.py`
- `keyword_injector.py`
- `models.py`
- `optimizer.py`
- `rest_validation.py`
- `rewriter.py`
- `template_engine.py`
- `translation.py`

### 子目录

- `api/`
- `data/`
- `knowledge/`
- `llm/`
- `prompts_db/`
- `services/`
- `strategies/`
- `templates/` (1 子目录)
- `web/`

## 编辑规范

- 修改代码前先阅读对应模块的现有实现，理解接口契约
- 遵循项目 `.clinerules` 中的架构约束
- 新增文件需保持一致的命名风格
- 提交前运行 `pytest` 或 `npm test` 确保无回归
