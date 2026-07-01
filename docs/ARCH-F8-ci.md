# ARCH-F8: GitHub Actions CI

## 目标

PR 推 master → 自动跑全量测试 → 状态显示在 PR 页面。

## 设计

### 工作流文件

`.github/workflows/test.yml`：

```yaml
name: Tests
on:
  push:
    branches: [master, main]
  pull_request:
    branches: [master, main]

jobs:
  test:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    strategy:
      matrix:
        python-version: ['3.11']
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
          cache: 'pip'
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install playwright pytest-playwright
          playwright install chromium --with-deps
      - name: Run tests
        run: pytest tests/ -q --tb=short
      - name: Start server for E2E
        run: |
          python -m uvicorn prompt_engine.api.rest:app --port 8000 &
          sleep 3
      - name: Run E2E tests
        run: pytest tests/test_web_e2e.py -v
```

### 关键决策

| 决策 | 原因 |
|------|------|
| **触发 push + PR** | 双重保险（PR 触发 + push master 触发） |
| **Python 3.11** | 项目实际使用版本 |
| **timeout 5min** | 充足（实际 30s） |
| **pip cache** | 加速 2x |
| **Playwright with deps** | E2E 测试需要浏览器 |

### 测试矩阵

- ✅ 全量 pytest
- ✅ E2E 测试（Playwright）
- 🚧 Docker build（暂不验证，节省 CI 时间）

### 状态徽章

README 顶部可加：
```markdown
![Tests](https://github.com/Colinchiu007/prompt-engine/workflows/Tests/badge.svg)
```

## 文件结构

```
prompt-engine/
├── .github/
│   └── workflows/
│       └── test.yml    # 新增
```

## 不做什么

- ❌ **不跑 Docker build**：节省 5min CI 时间
- ❌ **不部署到 PyPI**：v0.10.0 暂不发包
- ❌ **不跑 lint (ruff/flake8)**：项目目前无 lint 配置
