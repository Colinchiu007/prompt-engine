"""AI Router OpenAI 兼容接入契约测试。"""

import asyncio
import os
import sys
import tempfile
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import yaml


def _write_config(provider="minimax"):
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".yaml",
        prefix="ai-router-test-",
        dir=str(Path(__file__).parent),
        delete=False,
        encoding="utf-8",
    )
    path = handle.name
    handle.write(
        yaml.safe_dump(
            {
                "llm": {
                    "provider": provider,
                    "minimax": {
                        "api_key": "minimax-test-key",
                        "base_url": "https://minimax.example/v1",
                        "model": "MiniMax-M3",
                    },
                },
                "engine": {"default_platform": "generic"},
                "server": {"port": 8013},
                "platforms": {"generic": {"enabled": True}},
            },
            sort_keys=False,
        ),
    )
    handle.close()
    return path


def test_ai_router_env_builds_explicit_profile(monkeypatch):
    """显式选择 ai_router 时应从专用环境变量构建 OpenAI 兼容配置。"""
    from prompt_engine.config import load_config

    path = _write_config()
    monkeypatch.setenv("LLM_PROVIDER", "ai_router")
    monkeypatch.setenv("AI_ROUTER_PROJECT_KEY", "project-test-key")
    monkeypatch.setenv("AI_ROUTER_BASE_URL", "https://router.example/v1")
    monkeypatch.delenv("AI_ROUTER_MODEL", raising=False)

    try:
        config = load_config(path)
    finally:
        os.unlink(path)

    assert config["llm"]["provider"] == "ai_router"
    assert config["llm"]["ai_router"] == {
        "api_key": "project-test-key",
        "base_url": "https://router.example/v1",
        "model": "auto",
    }


def test_ai_router_opt_in_does_not_change_default_provider(monkeypatch):
    """未显式启用网关时，现有 MiniMax 默认值必须保持不变。"""
    from prompt_engine.config import load_config

    path = _write_config()
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("AI_ROUTER_PROJECT_KEY", raising=False)
    monkeypatch.delenv("AI_ROUTER_BASE_URL", raising=False)

    try:
        config = load_config(path)
    finally:
        os.unlink(path)

    assert config["llm"]["provider"] == "minimax"
    assert "ai_router" not in config["llm"]


def _ensure_openai_module(monkeypatch):
    """在未安装可选 SDK 的测试运行时注入最小模块桩。"""
    if "openai" not in sys.modules:
        module = types.ModuleType("openai")
        module.OpenAI = MagicMock(name="OpenAI")
        monkeypatch.setitem(sys.modules, "openai", module)


def test_ai_router_provider_passes_auto_model_to_openai(monkeypatch):
    """网关 Provider 必须把 auto 作为模型名原样发给兼容接口。"""
    _ensure_openai_module(monkeypatch)
    from prompt_engine.llm.base import BaseLLMProvider

    fake_response = MagicMock()
    fake_response.choices = [MagicMock(message=MagicMock(content="ok"))]
    fake_response.usage = MagicMock(total_tokens=3)
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = fake_response

    with patch("prompt_engine.llm.openai_compat.OpenAI", return_value=fake_client) as openai:
        provider = BaseLLMProvider.from_config(
            {
                "llm": {
                    "provider": "ai_router",
                    "ai_router": {
                        "api_key": "project-test-key",
                        "base_url": "https://router.example/v1",
                        "model": "auto",
                    },
                }
            }
        )
        result = provider.chat([{"role": "user", "content": "你好"}])

    openai.assert_called_once_with(
        api_key="project-test-key",
        base_url="https://router.example/v1",
        max_retries=3,
    )
    assert provider.model_name == "auto"
    assert result == ("ok", 3)
    assert fake_client.chat.completions.create.call_args.kwargs["model"] == "auto"


def test_key_router_can_create_ai_router_provider(monkeypatch):
    """KeyRouter 应能在没有 OpsCenter 密钥时使用网关项目密钥。"""
    _ensure_openai_module(monkeypatch)
    from prompt_engine.key_router import KeyRouter

    router = KeyRouter()
    router._config = {
        "llm": {
            "ai_router": {
                "api_key": "project-test-key",
                "base_url": "https://router.example/v1",
                "model": "auto",
            }
        }
    }

    async def create_provider():
        with patch(
            "prompt_engine.key_router.fetch_official_keys",
            new=AsyncMock(return_value=[]),
        ):
            return await router.get_provider("ai_router", user_tier=1)

    provider = asyncio.run(create_provider())

    assert provider._key_source == "config"
    assert provider.model_name == "auto"
    assert provider.config["api_key"] == "project-test-key"
    assert provider.config["base_url"] == "https://router.example/v1"
