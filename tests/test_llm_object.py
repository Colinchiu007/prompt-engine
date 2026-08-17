"""v0.20.x — BYOK llm 对象契约测试

覆盖：
  - BaseLLMProvider.from_llm_object：sensenova 默认 base_url / openai_compat 缺省 base_url /
    缺 api_key / 缺 model / 未知 provider / 非 dict → ValueError（rest 映射 422，api_key 绝不泄露）
  - REST /v1/optimize：缺省 llm 请求缺 llm → 422 fail-closed，与 creative_level 无关
  - 模板直出（图片显式 template）免 llm → 200
  - llm 路径结果 key_source=caller 且 caller 透传
  - batch：全带 llm 200 / 任一需 LLM 缺 llm → 422
  - 缓存键并入调用方 + provider 身份，防跨产品串缓存
  - 手动重生成可 bypass_cache，跳过缓存读写并通过 cache_hit 证明真实执行
"""
import pytest
from fastapi.testclient import TestClient

from prompt_engine.llm.base import BaseLLMProvider
from prompt_engine.optimizer import Optimizer


def _llm(provider="openai_compat", model="gpt-4o", api_key="sk-test-not-secret", base_url=None, caller=None):
    payload = {"provider": provider, "model": model, "api_key": api_key}
    if base_url:
        payload["base_url"] = base_url
    if caller:
        payload["caller"] = caller
    return payload


class TestFromLlmObject:
    """from_llm_object：调用方 llm 对象 → provider 实例的工厂契约。"""

    def test_sensenova_default_base_url(self):
        provider = BaseLLMProvider.from_llm_object(_llm(provider="sensenova", model="nova-pro"))
        assert provider.config["base_url"] == "https://token.sensenova.cn/v1"
        assert provider.config["api_key"] == "sk-test-not-secret"

    def test_sensenova_explicit_base_url_wins(self):
        provider = BaseLLMProvider.from_llm_object(
            _llm(provider="sensenova", base_url="https://custom.example/v1")
        )
        assert provider.config["base_url"] == "https://custom.example/v1"

    def test_openai_compat_default_base_url(self):
        provider = BaseLLMProvider.from_llm_object(_llm(provider="openai_compat"))
        assert provider.config["base_url"] == "https://api.openai.com/v1"

    def test_ai_router_default_base_url(self):
        provider = BaseLLMProvider.from_llm_object(_llm(provider="ai_router"))
        assert provider.config["base_url"] == "https://api.openai.com/v1"

    def test_deepseek_resolves_registered_provider(self):
        provider = BaseLLMProvider.from_llm_object(_llm(provider="deepseek", model="deepseek-v4-flash"))
        assert provider.__class__.__name__ == "DeepSeekProvider"

    def test_missing_api_key_fails_closed(self):
        with pytest.raises(ValueError, match="llm.api_key 必填"):
            BaseLLMProvider.from_llm_object({"provider": "openai_compat", "model": "gpt-4o"})

    def test_missing_model_fails_closed(self):
        with pytest.raises(ValueError, match="llm.model 必填"):
            BaseLLMProvider.from_llm_object({"provider": "openai_compat", "api_key": "sk-x"})

    def test_unknown_provider_raises_with_registry(self):
        with pytest.raises(ValueError) as exc:
            BaseLLMProvider.from_llm_object(_llm(provider="bogus"))
        assert "不支持的 LLM 供应商" in str(exc.value)
        assert "sensenova" in str(exc.value)

    def test_non_dict_llm_raises(self):
        with pytest.raises(ValueError, match="llm 必须是对象"):
            BaseLLMProvider.from_llm_object("not-a-dict")

    def test_api_key_never_leaks_into_error(self):
        """错误消息不得包含调用方 api_key 明文。"""
        secret = "sk-super-secret-value-12345"
        with pytest.raises(ValueError) as exc:
            BaseLLMProvider.from_llm_object({"provider": "bogus", "model": "m", "api_key": secret})
        assert secret not in str(exc.value)


class TestOptimizeEndpointByok:
    def test_explicit_llm_strategy_at_low_creative_level_uses_caller_llm(self, monkeypatch):
        client = self._client_with_mocked_llm(monkeypatch)
        resp = client.post("/v1/optimize", json={
            "prompt": "一位扶余王子在山城落脚",
            "platform": "generic",
            "creative_level": 1,
            "optimization_strategy": "llm",
            "llm": _llm(provider="sensenova", model="SenseNova", caller="multi-publish-desktop"),
        })
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["strategy_used"] == "llm"
        assert data["key_source"] == "caller"
        assert data["caller"] == "multi-publish-desktop"

    def test_explicit_template_strategy_ignores_creative_level_and_needs_no_llm(self):
        client = TestClient(self._app())
        resp = client.post("/v1/optimize", json={
            "prompt": "a cat",
            "platform": "generic",
            "creative_level": 8,
            "optimization_strategy": "template",
        })
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["strategy_used"] == "template"
        assert data["model_used"] == "template"
        assert data["key_source"] == "none"

    def test_explicit_template_strategy_rejects_video_domain(self):
        client = TestClient(self._app())
        resp = client.post("/v1/optimize", json={
            "prompt": "a cat running",
            "domain": "video",
            "platform": "generic_video",
            "creative_level": 1,
            "optimization_strategy": "template",
        })
        assert resp.status_code == 422, resp.text
        assert "template" in str(resp.json()["detail"])

    def test_top_level_caller_is_rejected(self, monkeypatch):
        client = self._client_with_mocked_llm(monkeypatch)
        resp = client.post("/v1/optimize", json={
            "prompt": "a cat",
            "platform": "generic",
            "llm": _llm(provider="sensenova", model="SenseNova"),
            "caller": "multi-publish-desktop",
        })
        assert resp.status_code == 422, resp.text
        assert "caller" in resp.text

    """REST /v1/optimize 的 BYOK fail-closed 契约。"""

    @pytest.fixture(autouse=True)
    def _no_cache(self, monkeypatch):
        monkeypatch.setattr(Optimizer, "_cache_get", lambda self, *a, **k: None)
        monkeypatch.setattr(Optimizer, "_cache_set", lambda self, *a, **k: None)

    def _client_with_mocked_llm(self, monkeypatch, llm_text=("enhanced image prompt", 100)):
        from prompt_engine.api import rest

        optimizer = Optimizer()
        monkeypatch.setattr(optimizer, "_call_llm", lambda system, user, variant=0: llm_text)
        monkeypatch.setattr(rest, "get_optimizer", lambda: optimizer)
        return TestClient(rest.app)

    def test_video_missing_llm_422(self):
        client = TestClient(self._app())
        resp = client.post("/v1/optimize", json={
            "prompt": "a cat running",
            "domain": "video",
            "platform": "generic_video",
            "creative_level": 5,
        })
        assert resp.status_code == 422
        assert "llm 必填" in resp.json()["detail"]

    def test_image_default_strategy_missing_llm_422(self, monkeypatch):
        client = self._client_with_mocked_llm(monkeypatch)
        resp = client.post("/v1/optimize", json={
            "prompt": "a majestic cat",
            "platform": "generic",
            "creative_level": 1,
        })
        assert resp.status_code == 422
        assert "llm 必填" in resp.json()["detail"]

    def test_explicit_template_path_no_llm_200(self):
        client = TestClient(self._app())
        resp = client.post("/v1/optimize", json={
            "prompt": "a cat",
            "platform": "generic",
            "creative_level": 1,
            "optimization_strategy": "template",
        })
        assert resp.status_code == 200, resp.text
        assert resp.json()["tokens_used"] == 0

    def test_llm_path_sets_key_source_caller_and_passthrough_caller(self, monkeypatch):
        client = self._client_with_mocked_llm(monkeypatch)
        resp = client.post("/v1/optimize", json={
            "prompt": "a majestic cat",
            "platform": "generic",
            "creative_level": 5,
            "llm": _llm(provider="sensenova", model="nova-pro", caller="multi-publish-desktop"),
        })
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["key_source"] == "caller"
        assert data["caller"] == "multi-publish-desktop"
        assert data["error"] is None
        assert "enhanced image prompt" in data["optimized_prompt"]

    def test_unknown_provider_in_llm_422(self, monkeypatch):
        client = self._client_with_mocked_llm(monkeypatch)
        resp = client.post("/v1/optimize", json={
            "prompt": "a majestic cat",
            "platform": "generic",
            "creative_level": 5,
            "llm": _llm(provider="bogus"),
        })
        assert resp.status_code == 422
        assert "不支持的 LLM 供应商" in resp.json()["detail"]

    def test_low_creative_with_llm_still_caller(self, monkeypatch):
        """低 creative_level 的缺省 llm 策略使用调用方绑定。"""
        client = self._client_with_mocked_llm(monkeypatch)
        resp = client.post("/v1/optimize", json={
            "prompt": "a cat",
            "platform": "generic",
            "creative_level": 1,
            "llm": _llm(),
        })
        assert resp.status_code == 200, resp.text
        assert resp.json()["strategy_used"] == "llm"
        assert resp.json()["key_source"] == "caller"

    def test_auto_strategy_rejected_by_schema(self):
        client = TestClient(self._app())
        resp = client.post("/v1/optimize", json={
            "prompt": "a cat",
            "platform": "generic",
            "optimization_strategy": "auto",
        })
        assert resp.status_code == 422

    def test_strategy_resolver_rejects_unknown_value_when_model_validation_is_bypassed(self):
        from types import SimpleNamespace
        from prompt_engine.models import DomainType
        from prompt_engine.optimizer import resolve_optimization_strategy

        request = SimpleNamespace(
            optimization_strategy="auto",
            domain=DomainType.IMAGE,
        )
        with pytest.raises(ValueError, match="optimization_strategy"):
            resolve_optimization_strategy(request)

    @staticmethod
    def _app():
        from prompt_engine.api.rest import app
        return app


class TestBatchByok:
    @pytest.fixture(autouse=True)
    def _no_cache(self, monkeypatch):
        monkeypatch.setattr(Optimizer, "_cache_get", lambda self, *a, **k: None)
        monkeypatch.setattr(Optimizer, "_cache_set", lambda self, *a, **k: None)

    def _client_with_mocked_llm(self, monkeypatch):
        from prompt_engine.api import rest

        optimizer = Optimizer()
        monkeypatch.setattr(optimizer, "_call_llm", lambda system, user, variant=0: ("scene prompt", 50))
        monkeypatch.setattr(rest, "get_optimizer", lambda: optimizer)
        return TestClient(rest.app)

    def test_batch_all_with_llm_200(self, monkeypatch):
        client = self._client_with_mocked_llm(monkeypatch)
        resp = client.post("/v1/optimize/batch", json={
            "requests": [
                {"prompt": "scene one", "domain": "video", "platform": "generic_video",
                 "creative_level": 5, "llm": _llm()},
                {"prompt": "image scene", "platform": "generic",
                 "creative_level": 5, "llm": _llm()},
            ]
        })
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert len(data) == 2
        assert all(item["key_source"] == "caller" for item in data)

    def test_batch_requiring_llm_missing_llm_422(self, monkeypatch):
        client = self._client_with_mocked_llm(monkeypatch)
        resp = client.post("/v1/optimize/batch", json={
            "requests": [
                {"prompt": "image scene", "platform": "generic", "creative_level": 1},
                {"prompt": "video scene", "domain": "video", "platform": "generic_video", "creative_level": 5},
            ]
        })
        assert resp.status_code == 422
        assert "llm 必填" in resp.json()["detail"]


class TestCacheProviderIsolation:
    def test_default_llm_and_explicit_llm_share_effective_cache(self, monkeypatch):
        from prompt_engine.models import OptimizeRequest, PlatformType

        optimizer = Optimizer()
        prompt = "effective-cache-llm-" + __import__("uuid").uuid4().hex
        calls = []
        monkeypatch.setattr(optimizer, "_call_llm", lambda *args, **kwargs: calls.append((args, kwargs)) or ("fresh LLM prompt", 1))
        provider = type("TestProvider", (), {"model_name": "SenseNova"})()
        provider_id = "multi-publish-desktop|sensenova|SenseNova|key:test"

        defaulted = optimizer.optimize(
            OptimizeRequest(prompt=prompt, platform=PlatformType.GENERIC, creative_level=5),
            provider=provider, provider_id=provider_id,
        )
        explicit = optimizer.optimize(
            OptimizeRequest(prompt=prompt, platform=PlatformType.GENERIC, creative_level=5, optimization_strategy="llm"),
            provider=provider, provider_id=provider_id,
        )

        assert defaulted.strategy_used == "llm"
        assert explicit.strategy_used == "llm"
        assert len(calls) == 1
        assert explicit.cache_hit is True

    def test_cache_key_differs_across_provider_identity(self):
        from prompt_engine.cache import SqlitePromptCache

        base = dict(
            prompt="a cat", platform="generic", creative_level=5, max_length=500,
            negative_prompt="", num_candidates=1,
        )
        k1 = SqlitePromptCache.make_key(**base)
        k2 = SqlitePromptCache.make_key(**base, provider="openai_compat|gpt-4o|")
        k3 = SqlitePromptCache.make_key(**base, provider="sensenova|nova-pro|https://token.sensenova.cn/v1")
        assert k1 != k2
        assert k2 != k3
        k2_again = SqlitePromptCache.make_key(**base, provider="openai_compat|gpt-4o|")
        assert k2 == k2_again

    def test_cache_manager_forwards_provider_to_sqlite_l2(self, monkeypatch):
        """L2 SQLite 读写必须携带与 L1 相同的 provider 身份，避免双级缓存键不一致。"""
        from prompt_engine.cache_manager import CacheManager
        from prompt_engine.models import OptimizeResult

        cm = CacheManager()
        captured = {}

        def fake_get(self, *args, **kwargs):
            captured["get"] = kwargs.get("provider")
            return None

        def fake_set(self, *args, **kwargs):
            captured["set"] = kwargs.get("provider")

        monkeypatch.setattr(cm._sqlite_cache, "get", fake_get)
        monkeypatch.setattr(cm._sqlite_cache, "set", fake_set)
        identity = "sensenova|nova-pro|https://token.sensenova.cn/v1"
        cm.get("p", "generic", 5, 500, "", 1, provider=identity)
        cm.set(
            "p", "generic", 5, 500, "", 1,
            OptimizeResult(optimized_prompt="x", platform="generic"),
            provider=identity,
        )
        assert captured["get"] == identity
        assert captured["set"] == identity


class TestBypassCache:
    """手动重生成必须真实执行 LLM，不能把历史缓存误报为新结果。"""

    @staticmethod
    def _provider():
        return type("TestProvider", (), {"model_name": "SenseNova"})()

    def test_bypass_cache_skips_reads_and_writes_then_calls_llm(self, monkeypatch):
        from prompt_engine.models import OptimizeRequest, OptimizeResult, PlatformType

        optimizer = Optimizer()
        get_calls = []
        set_calls = []
        monkeypatch.setattr(optimizer, "_cache_get", lambda *args, **kwargs: get_calls.append((args, kwargs)) or OptimizeResult(
            optimized_prompt="stale cached prompt", platform=PlatformType.GENERIC, model_used="stale"
        ))
        monkeypatch.setattr(optimizer, "_cache_set", lambda *args, **kwargs: set_calls.append((args, kwargs)))
        llm_calls = []
        monkeypatch.setattr(optimizer, "_call_llm", lambda *args, **kwargs: llm_calls.append((args, kwargs)) or ("fresh generated prompt", 42))

        result = optimizer.optimize(
            OptimizeRequest(
                prompt="scene",
                platform=PlatformType.GENERIC,
                creative_level=1,
                optimization_strategy="llm",
                bypass_cache=True,
            ),
            provider=self._provider(),
            provider_id="multi-publish-desktop|sensenova|SenseNova|",
        )

        assert get_calls == []
        assert set_calls == []
        assert len(llm_calls) == 1
        assert result.optimized_prompt == "fresh generated prompt"
        assert result.cache_hit is False
        assert result.strategy_used == "llm"
        assert result.key_source == "caller"

    def test_normal_cache_hit_sets_cache_hit_without_calling_llm(self, monkeypatch):
        from prompt_engine.models import OptimizeRequest, OptimizeResult, PlatformType

        optimizer = Optimizer()
        cached = OptimizeResult(
            optimized_prompt="cached prompt",
            platform=PlatformType.GENERIC,
            model_used="SenseNova",
        )
        monkeypatch.setattr(optimizer, "_cache_get", lambda *args, **kwargs: cached)
        monkeypatch.setattr(optimizer, "_call_llm", lambda *args, **kwargs: pytest.fail("cache hit must not call LLM"))

        result = optimizer.optimize(
            OptimizeRequest(
                prompt="scene",
                platform=PlatformType.GENERIC,
                creative_level=1,
                optimization_strategy="llm",
            ),
            provider=self._provider(),
            provider_id="multi-publish-desktop|sensenova|SenseNova|",
        )

        assert result.optimized_prompt == "cached prompt"
        assert result.cache_hit is True
        assert result.strategy_used == "llm"
