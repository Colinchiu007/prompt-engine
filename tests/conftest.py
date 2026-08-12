# conftest.py
# 全局 fixture 和配置

import os
import tempfile

import pytest


@pytest.fixture(scope="session", autouse=True)
def _video_cache_isolation():
    """视频引擎 SQLite 缓存默认落仓库根目录；测试必须隔离到临时目录，避免跨用例/跨会话污染。"""
    os.environ["VIDEO_CACHE_DIR"] = tempfile.mkdtemp(prefix="vpe-cache-")
    os.environ.setdefault("VIDEO_CACHE_DISABLED", "")
    yield
