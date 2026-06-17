# ARCH-F14: README 英文版 + PyPI + 徽章

## README 英文版

`README.en.md` 从头编写，不翻译中文 README。目标读者：不知 prompt-engine 是什么的海外开发者。

### 结构

```
1. What is Prompt Engine? (一句话)
2. Features list (7 platforms, 25 dimensions, RAG, DSL)
3. Quick Start (pip install → CLI → Web → code)
4. API Reference (endpoints table)
5. Use Cases
6. Comparison
7. Contributing
8. License
```

## PyPI 发布

### 配置

`pyproject.toml` 已有，补全：
```toml
[project]
name = "prompt-engine-image"
version = "0.12.0"
description = "AI-powered image prompt optimization engine"
readme = "README.en.md"
requires-python = ">=3.10"
license = {text = "MIT"}
classifiers = [
    "Development Status :: 4 - Beta",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3",
]
```

### 发布脚本
```bash
pip install build twine
python -m build
python -m twine upload dist/*
```

## GitHub Actions 徽章

### Markdown 代码
```markdown
[![Tests](https://github.com/Colinchiu007/prompt-engine/actions/workflows/test.yml/badge.svg)](https://github.com/Colinchiu007/prompt-engine/actions)
```

### 放置位置
- README.md: 标题下方第一行
- README.en.md: 标题下方第一行