"""Gemini / DeepSeek / SiliconFlow 供应商测试"""
import pytest
from unittest.mock import patch, MagicMock


class TestGeminiProvider:
    """Google Gemini provider 测试."""

    def test_import_gemini_provider(self):
        from prompt_engine.llm.gemini import GeminiProvider
        assert GeminiProvider is not None

    def test_gemini_provider_init(self):
        from prompt_engine.llm.gemini import GeminiProvider
        provider = GeminiProvider(api_key="test-key", model="gemini-2.0-flash")
        assert provider.model_name == "gemini-2.0-flash"
        assert provider.api_key == "test-key"

    @patch("prompt_engine.llm.gemini.GeminiProvider.chat")
    def test_gemini_chat_mock(self, mock_chat):
        from prompt_engine.llm.gemini import GeminiProvider
        mock_chat.return_value = ("optimized prompt", 100)
        provider = GeminiProvider(api_key="test-key")
        result, tokens = provider.chat("system prompt", "user prompt")
        assert result == "optimized prompt"
        assert tokens == 100

    def test_gemini_from_config(self):
        from prompt_engine.llm.gemini import GeminiProvider
        config = {"api_key": "test-key", "model": "gemini-2.0-flash", "temperature": 0.7}
        provider = GeminiProvider.from_config(config)
        assert provider.model_name == "gemini-2.0-flash"
        assert provider.temperature == 0.7


class TestProviderRegistry:
    """供应商注册测试."""

    def test_provider_list_includes_gemini(self):
        from prompt_engine.llm import list_providers
        providers = list_providers()
        assert "gemini" in providers

    def test_create_gemini_provider(self):
        from prompt_engine.llm import create_provider
        provider = create_provider("gemini", api_key="test-key")
        assert provider is not None
        assert "gemini" in provider.model_name
