# conftest.py
# 全局 fixture 和配置

# 测试导入引导：让 04-tests 优先解析当前 worktree 源码，而不是
# site-packages 里 editable 安装（finder 指向主仓库）的版本。
import os
import sys

_WT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WT_ROOT not in sys.path:
    sys.path.insert(0, _WT_ROOT)
sys.meta_path = [
    finder for finder in getattr(sys, "meta_path", [])
    if not (getattr(finder, "__name__", "") or "").startswith("__editable__")
]

