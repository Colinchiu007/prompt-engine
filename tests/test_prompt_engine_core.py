"""共享内核（prompt_engine_core）语义锚定测试 — 防止迁移回归（评审 C1/M1/M2/M3）。"""
import json
from pathlib import Path

import pytest

from prompt_engine_core.llm import BaseLLMProvider
from prompt_engine_core.registry import StrategyRegistry
from prompt_engine_core.knowledge import load_seed_entries


class TestLLMCap:
    """W1：默认 16384 max_tokens cap 必须无条件生效（评审 C1 回归防护）。"""

    def _provider(self, **llm_overrides):
        cfg = {"llm": {"api_key": "k", "model": "m", "base_url": "http://x/v1", **llm_overrides}}
        p = BaseLLMProvider(cfg)
        calls = {}
        def fake_request(system_prompt, user_prompt, max_tokens=3000):
            calls["max_tokens"] = max_tokens
            return '{"ok": true}'
        p._request = fake_request
        return p, calls

    def test_default_cap_16384_when_unconfigured(self):
        p, calls = self._provider()
        p.call("s", "u", max_length=20000)
        assert calls["max_tokens"] == 16384

    def test_default_cap_also_applies_to_long_batch(self):
        p, calls = self._provider()
        p.call("s", "u", max_length=10000)
        # 动态 max_tokens = 20000 > 16384 → 仍封顶
        assert calls["max_tokens"] == 16384

    def test_configured_cap_follows_config(self):
        p, calls = self._provider(max_tokens_cap=30000)
        p.call("s", "u", max_length=20000)
        assert calls["max_tokens"] == 30000

    def test_small_max_length_below_cap_untouched(self):
        p, calls = self._provider()
        p.call("s", "u", max_length=1800)
        assert calls["max_tokens"] == 3600

    def test_no_api_key_fails_closed(self):
        p = BaseLLMProvider({"llm": {}})
        with pytest.raises(RuntimeError):
            p.call("s", "u")


class TestStrategyRegistrySemantics:
    """注册器：小写归一 + items() 保序（评审 M1/M2 锚定）。"""

    def test_register_lowercases_and_get_is_case_insensitive(self):
        reg = StrategyRegistry()
        @reg.register("FooBar")
        class S:  # noqa: F811
            pass
        assert reg.get("foobar") is S
        assert reg.get("FooBar") is S

    def test_items_preserves_insertion_order(self):
        reg = StrategyRegistry()
        @reg.register("zeta")
        class Z:
            pass
        @reg.register("alpha")
        class A:
            pass
        assert [k for k, _ in reg.items()] == ["zeta", "alpha"]
        # list() 保持字母序（视频引擎历史语义）
        assert reg.list() == ["alpha", "zeta"]

    def test_missing_returns_none(self):
        reg = StrategyRegistry()
        assert reg.get("nope") is None
        assert "nope" not in reg


class TestSeedLoaderDefaultPlatform:
    """种子加载：default_platform 仅作用于字段缺失；显式 platform 原样保留（评审 M3）。"""

    def test_missing_platform_uses_default(self, tmp_path):
        f = tmp_path / "seeds.json"
        f.write_text(json.dumps([{"prompt_text": "hello"}]), encoding="utf-8")
        entries = load_seed_entries(f, fallback_prefix="vseed", default_platform="generic_video")
        assert entries[0].platform == "generic_video"
        assert entries[0].id.startswith("vseed-")

    def test_explicit_platform_preserved(self, tmp_path):
        f = tmp_path / "seeds.json"
        f.write_text(json.dumps([{"prompt_text": "hello", "platform": "generic"}]), encoding="utf-8")
        entries = load_seed_entries(f, default_platform="generic_video")
        assert entries[0].platform == "generic"

    def test_prompt_fallback_key(self, tmp_path):
        f = tmp_path / "seeds.json"
        f.write_text(json.dumps([{"prompt": "legacy"}]), encoding="utf-8")
        entries = load_seed_entries(f)
        assert entries[0].prompt_text == "legacy"