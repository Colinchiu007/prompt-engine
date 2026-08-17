"""AI Router OpenAI compatible integration tests (BYOK mode).

In BYOK architecture, LLM config is no longer loaded from config.yaml.
Instead, callers pass LLM binding via the request's llm object.
This file tests BaseLLMProvider.from_llm_object for ai_router provider.
"""

import sys
import types
from unittest.mock import MagicMock, patch


def _ensure_openai_module(monkeypatch):
    if "openai" not in sys.modules:
        module = types.ModuleType("openai")
        module.OpenAI = MagicMock(name="OpenAI")
        monkeypatch.setitem(sys.modules, "openai", module)


def test_from_llm_object_creates_ai_router_provider():
    from prompt_engine.llm.base import BaseLLMProvider
    provider = BaseLLMProvider.from_llm_object({
        "provider": "ai_router",
        "model": "auto",
        "api_key": "project-test-key",
        "base_url": "https://router.example/v1",
    })
    assert provider.model_name == "auto"


def test_from_llm_object_rejects_missing_api_key():
    from prompt_engine.llm.base import BaseLLMProvider
    try:
        BaseLLMProvider.from_llm_object({"provider": "ai_router", "model": "auto"})
        assert False, "Should raise ValueError"
    except ValueError as e:
        assert "api_key" in str(e)


def test_from_llm_object_rejects_missing_model():
    from prompt_engine.llm.base import BaseLLMProvider
    try:
        BaseLLMProvider.from_llm_object({"provider": "ai_router", "api_key": "test-key"})
        assert False, "Should raise ValueError"
    except ValueError as e:
        assert "model" in str(e)


def test_ai_router_provider_passes_auto_model_to_openai(monkeypatch):
    _ensure_openai_module(monkeypatch)
    from prompt_engine.llm.base import BaseLLMProvider
    fake_response = MagicMock()
    fake_response.choices = [MagicMock(message=MagicMock(content="ok"))]
    fake_response.usage = MagicMock(total_tokens=3)
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = fake_response
    with patch("prompt_engine.llm.openai_compat.OpenAI", return_value=fake_client) as openai:
        provider = BaseLLMProvider.from_llm_object({
            "provider": "ai_router",
            "model": "auto",
            "api_key": "project-test-key",
            "base_url": "https://router.example/v1",
        })
        result = provider.chat([{"role": "user", "content": "hello"}])
    openai.assert_called_once_with(
        api_key="project-test-key",
        base_url="https://router.example/v1",
        max_retries=3,
    )
    assert provider.model_name == "auto"
    assert result == ("ok", 3)
    assert fake_client.chat.completions.create.call_args.kwargs["model"] == "auto"


def test_config_rejects_top_level_llm():
    import tempfile, os
    from pathlib import Path
    import yaml
    from prompt_engine.config import load_config
    handle = tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", prefix="ai-router-test-",
        dir=str(Path(__file__).parent), delete=False, encoding="utf-8",
    )
    path = handle.name
    handle.write(yaml.safe_dump({
        "llm": {"provider": "minimax", "minimax": {"api_key": "k", "model": "m"}},
        "engine": {"default_platform": "generic"},
    }, sort_keys=False))
    handle.close()
    try:
        load_config(path)
        assert False, "Should raise ValueError"
    except ValueError as e:
        assert "llm" in str(e)
    finally:
        os.unlink(path)
