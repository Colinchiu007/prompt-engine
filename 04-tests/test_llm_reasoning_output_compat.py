"""回归（2026-08-21）：OpenAI 兼容 provider 兼容推理模型输出。

背景：Multi-Publish 默认 LLM opencode-go(mimo-v2.5) 经 openai_compat 调 /v1/optimize
稳定返回「content 为空 / 仅推理内容」502。根因：OpenAICompatProvider 硬编码
max_tokens=500 + timeout=15，推理模型先思考后输出，预算/超时不足导致 message.content 为空；
桌面端同一网关成功调用未带 500 上限且耗时 27~53s。

修复语义：
- 未显式配置 max_tokens 时省略该字段（网关默认预算），显式配置仍透传；
- 默认 timeout 15 -> 120（显式配置覆盖）；
- content 为空 + reasoning_content 非空时记录 warning，返回空文本，不伪造提示词；
- prompt_engine_core/llm.py 对 message.content 安全读取（.get），缺键不抛 KeyError。
"""
import logging
from types import SimpleNamespace

import pytest

import prompt_engine_core.llm as core_llm
from prompt_engine.llm.openai_compat import OpenAICompatProvider


def _msg(content, reasoning=None, finish_reason="stop"):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content, reasoning_content=reasoning),
                finish_reason=finish_reason,
            )
        ],
        usage=SimpleNamespace(total_tokens=99),
    )


def _provider(config, create):
    p = OpenAICompatProvider(config)
    p._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    return p


class TestOpenAICompatOutputCompatibility:
    def test_default_omits_max_tokens_and_uses_120_timeout(self):
        captured = {}

        def fake_create(**kw):
            captured.update(kw)
            return _msg("hello")

        p = _provider({"api_key": "sk-test", "base_url": "https://x/v1"}, fake_create)
        text, tokens = p.chat([{"role": "user", "content": "hi"}])
        assert text == "hello"
        assert tokens == 99
        assert "max_tokens" not in captured
        assert captured["timeout"] == 120

    def test_explicit_max_tokens_still_forwarded(self):
        captured = {}

        def fake_create(**kw):
            captured.update(kw)
            return _msg("x")

        p = _provider({"api_key": "sk-test", "base_url": "https://x/v1", "max_tokens": 500}, fake_create)
        p.chat([{"role": "user", "content": "hi"}])
        assert captured.get("max_tokens") == 500
        assert captured.get("timeout") == 120

    def test_explicit_timeout_wins(self):
        captured = {}

        def fake_create(**kw):
            captured.update(kw)
            return _msg("x")

        p = _provider({"api_key": "sk-test", "base_url": "https://x/v1", "timeout": 30}, fake_create)
        p.chat([{"role": "user", "content": "hi"}])
        assert captured.get("timeout") == 30

    def test_reasoning_only_returns_empty_and_warns(self, caplog):
        p = _provider(
            {"api_key": "sk-test", "base_url": "https://x/v1"},
            lambda **kw: _msg(None, "thinking...", finish_reason="length"),
        )
        with caplog.at_level(logging.WARNING, logger="prompt_engine.llm.openai_compat"):
            text, tokens = p.chat([{"role": "user", "content": "hi"}])
        assert text == ""
        assert "content 为空" in caplog.text
        assert "finish_reason=length" in caplog.text


class TestCoreSafeRead:
    def test_missing_content_key_returns_none(self, monkeypatch):
        class _FakeResp:
            def read(self):
                return b'{"choices":[{"message":{}}]}'

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        def _fake_urlopen(req, timeout=None):
            return _FakeResp()

        monkeypatch.setattr(core_llm.urllib.request, "urlopen", _fake_urlopen)
        provider = core_llm.BaseLLMProvider({"llm": {"api_key": "sk", "base_url": "https://x/v1"}})
        assert provider._request("sys", "user") is None
