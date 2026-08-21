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
import json
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

    def test_reasoning_only_retry_succeeds_with_content(self):
        """Path 2：content 空 + reasoning 非空 -> 自动重试，第二次返回实际内容。"""
        call_count = 0

        def fake_create(**kw):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _msg(None, "thinking...", finish_reason="length")
            return _msg("optimized_prompt_here", None)

        p = _provider({"api_key": "sk-test", "base_url": "https://x/v1"}, fake_create)
        text, tokens = p.chat([{"role": "user", "content": "hi"}])
        assert text == "optimized_prompt_here"
        assert tokens == 99
        assert call_count == 2  # 一次重试

    def test_reasoning_only_returns_empty_after_retry_fails(self, caplog):
        """Path 2：content 空 + reasoning 非空 -> 重试仍为空，fail-closed 返回空文本。"""
        call_count = 0

        def fake_create(**kw):
            nonlocal call_count
            call_count += 1
            return _msg(None, "thinking...", finish_reason="length")

        p = _provider({"api_key": "sk-test", "base_url": "https://x/v1"}, fake_create)
        with caplog.at_level(logging.WARNING, logger="prompt_engine.llm.openai_compat"):
            text, tokens = p.chat([{"role": "user", "content": "hi"}])
        assert text == ""
        assert call_count == 3  # 两次重试
        assert "重试" in caplog.text
        assert "finish_reason=length" in caplog.text

    def test_normal_response_no_retry(self):
        """Path 2：普通模型 content 非空 -> 不触发重试，单次调用。"""
        call_count = 0

        def fake_create(**kw):
            nonlocal call_count
            call_count += 1
            return _msg("real content")

        p = _provider({"api_key": "sk-test", "base_url": "https://x/v1"}, fake_create)
        text, tokens = p.chat([{"role": "user", "content": "hi"}])
        assert text == "real content"
        assert call_count == 1  # 无重试


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


class TestCoreReasoningRetry:
    """Path 2：共享内核 _request() 对推理模型的自动重试。"""

    @staticmethod
    def _make_provider():
        return core_llm.BaseLLMProvider({"llm": {"api_key": "sk", "base_url": "https://x/v1", "model": "mimo-v2.5"}})

    @staticmethod
    def _make_resp(content, reasoning=""):
        class _FakeResp:
            def __init__(self, payload):
                self._payload = payload

            def read(self):
                return self._payload

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        return _FakeResp(json.dumps({
            "choices": [{"message": {"content": content, "reasoning_content": reasoning}}],
        }).encode())

    def test_reasoning_only_triggers_retry_and_succeeds(self, monkeypatch):
        """Path 2：content 空 + reasoning 非空 -> 自动重试，第二次返回内容。"""
        call_count = 0
        responses = [
            self._make_resp(None, "thinking..."),
            self._make_resp("actual response", ""),
        ]

        def _fake_urlopen(req, timeout=None):
            nonlocal call_count
            resp = responses[call_count]
            call_count += 1
            return resp

        monkeypatch.setattr(core_llm.urllib.request, "urlopen", _fake_urlopen)
        provider = self._make_provider()
        result = provider._request("sys", "user")
        assert result == "actual response"
        assert call_count == 2  # 一次重试

    def test_reasoning_only_retry_still_empty_returns_none(self, monkeypatch, caplog):
        """Path 2：content 空 + reasoning 非空 -> 重试仍为空，返回 None（fail-closed）。"""
        call_count = 0

        def _fake_urlopen(req, timeout=None):
            nonlocal call_count
            call_count += 1
            return self._make_resp(None, "more thinking...")

        monkeypatch.setattr(core_llm.urllib.request, "urlopen", _fake_urlopen)
        provider = self._make_provider()
        with caplog.at_level(logging.WARNING, logger="prompt_engine_core.llm"):
            result = provider._request("sys", "user")
        assert result is None
        assert call_count == 3  # 两次重试
        assert "重试" in caplog.text

    def test_normal_response_no_retry(self, monkeypatch):
        """Path 2：content 非空 -> 不触发重试，单次调用。"""
        call_count = 0

        def _fake_urlopen(req, timeout=None):
            nonlocal call_count
            call_count += 1
            return self._make_resp("real content", "")

        monkeypatch.setattr(core_llm.urllib.request, "urlopen", _fake_urlopen)
        provider = self._make_provider()
        result = provider._request("sys", "user")
        assert result == "real content"
        assert call_count == 1  # 无重试

    def test_empty_content_no_reasoning_no_retry(self, monkeypatch):
        """Path 2：content 空但没有 reasoning -> 不触发重试（非推理模型）。"""
        call_count = 0

        def _fake_urlopen(req, timeout=None):
            nonlocal call_count
            call_count += 1
            return self._make_resp(None, "")  # content 空，无 reasoning

        monkeypatch.setattr(core_llm.urllib.request, "urlopen", _fake_urlopen)
        provider = self._make_provider()
        result = provider._request("sys", "user")
        assert result is None
        assert call_count == 1  # 无重试（不是推理模型）

class TestReasoningRecoveryHardening:
    def test_retry_boosts_small_explicit_max_tokens(self):
        captured = {}

        def fake_create(**kw):
            if "max_tokens" in kw:
                captured["retry_max_tokens"] = kw["max_tokens"]
            captured["calls"] = captured.get("calls", 0) + 1
            if captured["calls"] == 1:
                return _msg(None, "thinking", finish_reason="length")
            return _msg("optimized_prompt_here", None)

        p = _provider({"api_key": "sk-test", "base_url": "https://x/v1", "max_tokens": 500}, fake_create)
        text, _ = p.chat([{"role": "user", "content": "hi"}])
        assert text == "optimized_prompt_here"
        assert captured["retry_max_tokens"] == 8192

    def test_second_retry_adds_final_output_system_instruction(self):
        calls = []

        def fake_create(**kw):
            calls.append(kw["messages"])
            if len(calls) <= 2:
                return _msg(None, "thinking", finish_reason="length")
            return _msg("optimized_prompt_here", None)

        p = _provider({"api_key": "sk-test", "base_url": "https://x/v1"}, fake_create)
        text, _ = p.chat([{"role": "user", "content": "hi"}])
        assert text == "optimized_prompt_here"
        assert calls[2][-1]["role"] == "system"
        assert "content field" in calls[2][-1]["content"]
