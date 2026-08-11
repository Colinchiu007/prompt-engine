"""MiniMax LLM Provider 配置测试（仅构造，不发起网络请求）"""
from prompt_engine.llm.minimax import MiniMaxProvider


def test_minimax_provider_reads_max_tokens_from_config():
    provider = MiniMaxProvider({"api_key": "test-key", "max_tokens": 1500, "model": "MiniMax-M3"})
    assert provider._max_tokens == 1500


def test_minimax_provider_class_default_fallback():
    provider = MiniMaxProvider({"api_key": "test-key"})
    assert provider._max_tokens == 500
