"""v0.11.0 — 用户掌控优化（关键词 + 风格 + 扩写）"""
import pytest
from fastapi.testclient import TestClient


class TestKeywordsUI:
    """F1: 关键词注入可视化."""

    def test_keywords_endpoint_returns_list(self):
        """GET /v1/keywords 应返回关键词列表"""
        from prompt_engine.api.rest import app
        client = TestClient(app)
        resp = client.get("/v1/keywords?platform=midjourney")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) > 0, "Should return keywords"

    def test_keywords_vary_by_platform(self):
        """不同平台返回不同关键词"""
        from prompt_engine.api.rest import app
        client = TestClient(app)
        mj = client.get("/v1/keywords?platform=midjourney").json()
        sd = client.get("/v1/keywords?platform=stable_diffusion").json()
        assert mj != sd, "Keywords should differ by platform"


class TestStyleSelector:
    """F2: 25 风格维度选择器."""

    def test_style_categories_endpoint(self):
        """GET /v1/styles/categories 返回 25 个风格"""
        from prompt_engine.api.rest import app
        client = TestClient(app)
        resp = client.get("/v1/styles/categories")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 25
        assert len(data["categories"]) == 25

    def test_style_param_in_optimize(self):
        """优化请求中指定 style 应被后端接受"""
        from prompt_engine.api.rest import app
        from prompt_engine.models import OptimizeRequest, StyleType
        req = OptimizeRequest(
            prompt="a cat",
            platform="midjourney",
            style=StyleType.FANTASY
        )
        assert req.style == StyleType.FANTASY


class TestRewriteUI:
    """F3: 扩写 UI."""

    def test_rewrite_endpoint_works_with_caller_llm(self, monkeypatch):
        """POST /v1/rewrite 返回扩写结果"""
        from prompt_engine.api import rest
        from prompt_engine.models import OptimizeResult
        from prompt_engine.optimizer import Optimizer

        optimizer = Optimizer()
        monkeypatch.setattr(
            optimizer,
            "rewrite",
            lambda request, provider, provider_id: OptimizeResult(
                optimized_prompt="a detailed cat prompt",
                platform=request.platform,
                model_used="test-model",
                key_source="caller",
                strategy_used="llm",
                caller=request.llm.caller if request.llm else None,
            ),
        )
        monkeypatch.setattr(rest, "get_optimizer", lambda: optimizer)
        client = TestClient(rest.app)
        resp = client.post("/v1/rewrite", json={
            "prompt": "a cat",
            "platform": "midjourney",
            "max_length": 300,
            "llm": {"provider": "openai_compat", "model": "test-model", "api_key": "test-key", "caller": "test-client"},
        })
        assert resp.status_code == 200, resp.text
        assert resp.json()["key_source"] == "caller"
        assert resp.json()["caller"] == "test-client"

    def test_rewrite_requires_caller_llm(self):
        """没有调用方 LLM 绑定时必须 fail-closed。"""
        from prompt_engine.api.rest import app
        client = TestClient(app)
        resp = client.post("/v1/rewrite", json={
            "prompt": "a cat",
            "platform": "midjourney",
            "max_length": 300,
        })
        assert resp.status_code == 422

    def test_rewrite_requires_text(self):
        """空 prompt 应返回 422"""
        from prompt_engine.api.rest import app
        client = TestClient(app)
        resp = client.post("/v1/rewrite", json={
            "prompt": "",
            "platform": "midjourney"
        })
        assert resp.status_code == 422
