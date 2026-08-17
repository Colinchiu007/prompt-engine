"""Embedding 配置必须与文字 LLM 配置完全解耦。"""

import pytest

from prompt_engine.knowledge import embedder as embedder_module
from prompt_engine.knowledge.embedder import PromptEmbedder


class _FakeOpenAI:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


def test_from_config_reads_only_knowledge_embedding(monkeypatch):
    monkeypatch.setattr(embedder_module, "OpenAI", _FakeOpenAI)

    instance = PromptEmbedder.from_config({
        "llm": {
            "provider": "minimax",
            "minimax": {"api_key": "must-not-be-used"},
        },
        "knowledge": {
            "embedding": {
                "api_key": "embedding-key",
                "base_url": "https://embedding.example/v1",
                "model": "embedding-model",
            },
        },
    })

    assert instance._client.kwargs == {
        "api_key": "embedding-key",
        "base_url": "https://embedding.example/v1",
    }
    assert instance._model == "embedding-model"


def test_from_config_without_embedding_key_fails_closed():
    with pytest.raises(ValueError, match="knowledge.embedding.api_key 必填"):
        PromptEmbedder.from_config({"knowledge": {"embedding": {"model": "x"}}})
