"""v0.20.x — BYOK llm 对象契约测试

覆盖：
  - BaseLLMProvider.from_llm_object：sensenova 默认 base_url / openai_compat 缺省 base_url /
    缺 api_key / 缺 model / 未知 provider / 非 dict → ValueError（rest 映射 422，api_key 绝不泄露）
  - REST /v1/optimize：需 LLM 请求（video 域 / 图片 creative_level>3）缺 llm → 422 fail-closed
  - 模板直出（图片 creative_level<=3）免 llm → 200
  - llm 路径结果 key_source=caller 且 caller 透传
  - batch：全带 llm 200 / 任一需 LLM 缺 llm → 422
  - 缓存键并入 provider 身份（provider|model|base_url），防跨调用方串缓存
"""
import pytest
from fastapi.testclient import TestClient

from prompt_engine.llm.base import BaseLLMProvider
from prompt_engine.optimizer import Optimizer


def _llm(provider="openai_compat", model="gpt-4o", api_key="sk-test-not-secret", base_url=None):
    payload = {"provider": provider, "model": model, "api_key": api_key}
    if base_url:
        payload["base_url"] = base_url
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

    def test_image_creative5_missing_llm_422(self, monkeypatch):
        client = self._client_with_mocked_llm(monkeypatch)
        resp = client.post("/v1/optimize", json={
            "prompt": "a majestic cat",
            "platform": "generic",
            "creative_level": 5,
        })
        assert resp.status_code == 422
        assert "llm 必填" in resp.json()["detail"]

    def test_template_path_no_llm_200(self):
        client = TestClient(self._app())
        resp = client.post("/v1/optimize", json={
            "prompt": "a cat",
            "platform": "generic",
            "creative_level": 1,
        })
        assert resp.status_code == 200, resp.text
        assert resp.json()["tokens_used"] == 0

    def test_llm_path_sets_key_source_caller_and_passthrough_caller(self, monkeypatch):
        client = self._client_with_mocked_llm(monkeypatch)
        resp = client.post("/v1/optimize", json={
            "prompt": "a majestic cat",
            "platform": "generic",
            "creative_level": 5,
            "llm": _llm(provider="sensenova", model="nova-pro"),
            "caller": "multi-publish-desktop",
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
        """creative_level<=3 模板路径即使带 llm 也免 LLM（key_source 保持 config 语义）。"""
        client = self._client_with_mocked_llm(monkeypatch)
        resp = client.post("/v1/optimize", json={
            "prompt": "a cat",
            "platform": "generic",
            "creative_level": 1,
            "llm": _llm(),
        })
        assert resp.status_code == 200, resp.text
        assert resp.json()["key_source"] == "config"

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
                {"prompt": "template image", "platform": "generic", "creative_level": 1},
                {"prompt": "video scene", "domain": "video", "platform": "generic_video", "creative_level": 5},
            ]
        })
        assert resp.status_code == 422
        assert "llm 必填" in resp.json()["detail"]


class TestCacheProviderIsolation:
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
