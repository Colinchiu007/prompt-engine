"""引擎资源端点测试 + 图片预览端点测试."""
import pytest
from unittest.mock import patch


class TestEngineResources:
    """F1: 引擎资源展示端点."""

    def test_resources_returns_full_info(self):
        from prompt_engine.api.rest import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        resp = client.get("/v1/resources")
        assert resp.status_code == 200
        data = resp.json()
        assert "platforms" in data
        assert "rag_cases" in data
        assert "mj_keywords" in data
        assert "style_dimensions" in data
        assert "llm_providers" in data
        assert "wildcards" in data
        assert "templates" in data

    def test_resources_has_correct_count(self):
        from prompt_engine.api.rest import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        resp = client.get("/v1/resources")
        data = resp.json()
        assert data["style_dimensions"] == 25
        assert data["platforms"] >= 7
        assert data["llm_providers"] >= 3
        assert data["rag_cases"] >= 500  # prompts_db (918) + seed_prompts (18) = ~936


class TestImagePreview:
    """F2: 图片预览端点."""

    def test_preview_returns_url(self):
        from prompt_engine.api.rest import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        resp = client.post("/v1/preview", json={"prompt": "a cat", "model": "picsum"})
        assert resp.status_code == 200
        data = resp.json()
        assert "url" in data
        assert "model" in data

    def test_preview_default_model(self):
        from prompt_engine.api.rest import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        # 不指定 model
        resp = client.post("/v1/preview", json={"prompt": "a cat"})
        assert resp.status_code == 200

    def test_preview_rejects_empty_prompt(self):
        from prompt_engine.api.rest import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        resp = client.post("/v1/preview", json={"prompt": "", "model": "picsum"})
        assert resp.status_code == 400


class TestImageModels:
    """F3: 图片模型配置端点."""

    def test_list_models(self):
        from prompt_engine.api.rest import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        resp = client.get("/v1/image-models")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 5  # 至少 5 个预设模型

    def test_models_have_required_fields(self):
        from prompt_engine.api.rest import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        resp = client.get("/v1/image-models")
        models = resp.json()
        for m in models:
            assert "id" in m
            assert "name" in m
            assert "provider" in m
            assert "requires_key" in m

