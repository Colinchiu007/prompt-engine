# -*- coding: utf-8 -*-
"""cli.py — API Key 解析契约测试（Stage -1.3：Key 移出 argv）

覆盖：
  - --api-key 参数缺省时，从环境变量 PROMPT_ENGINE_API_KEY 读取（不清空，不落 argv）
  - --api-key 参数与 env 同时存在时，参数优先
  - 两者皆缺 → fail-closed SystemExit
"""
import os

import pytest

from prompt_engine.cli import _resolve_api_key


class _Args:
    def __init__(self, api_key=""):
        self.api_key = api_key


@pytest.fixture(autouse=True)
def _clear_env_key():
    """每个用例前清除 env key，避免污染。"""
    saved = os.environ.pop("PROMPT_ENGINE_API_KEY", None)
    yield
    if saved is not None:
        os.environ["PROMPT_ENGINE_API_KEY"] = saved
    else:
        os.environ.pop("PROMPT_ENGINE_API_KEY", None)


def test_env_key_read_when_argv_missing():
    os.environ["PROMPT_ENGINE_API_KEY"] = "sk-env-secret"
    assert _resolve_api_key(_Args(api_key="")) == "sk-env-secret"


def test_argv_key_takes_priority_over_env():
    os.environ["PROMPT_ENGINE_API_KEY"] = "sk-env-secret"
    assert _resolve_api_key(_Args(api_key="sk-argv-secret")) == "sk-argv-secret"


def test_env_key_stripped():
    os.environ["PROMPT_ENGINE_API_KEY"] = "  sk-env-padded  "
    assert _resolve_api_key(_Args(api_key="")) == "sk-env-padded"


def test_missing_key_fails_closed():
    with pytest.raises(SystemExit) as exc:
        _resolve_api_key(_Args(api_key=""))
    msg = str(exc.value)
    assert "PROMPT_ENGINE_API_KEY" in msg
    assert "template" in msg