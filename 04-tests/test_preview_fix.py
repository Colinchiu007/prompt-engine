"""图片预览修复测试（v0.9.2）"""


class TestPreviewFix:
    """图片预览 Picsum 替代 Pollinations 测试."""

    def test_picsum_default_model(self):
        """Picsum 应为新默认模型."""
        from prompt_engine.api.rest import IMAGE_MODELS
        default = next((m for m in IMAGE_MODELS if m["id"] == "picsum"), None)
        assert default is not None
        assert default["requires_key"] is False
        assert default["endpoint"].startswith("https://picsum.photos/")

    def test_pollinations_marked_deprecated(self):
        """Pollinations 应标记失效."""
        from prompt_engine.api.rest import IMAGE_MODELS
        pollin = next((m for m in IMAGE_MODELS if m["id"] == "pollinations"), None)
        if pollin:
            assert "失效" in pollin.get("description", "") or "已失效" in pollin.get("description", "") or "402" in pollin.get("description", "")

    def test_preview_endpoint_picsum(self):
        """preview 端点应支持 picsum 模型."""
        from fastapi.testclient import TestClient
        from prompt_engine.api.rest import app
        client = TestClient(app)
        r = client.post("/v1/preview", json={"prompt": "test", "model": "picsum", "width": 800, "height": 600})
        assert r.status_code == 200
        data = r.json()
        assert "picsum.photos" in data["url"]

    def test_picsum_url_deterministic(self):
        """同一 prompt 应产生同一 URL."""
        from fastapi.testclient import TestClient
        from prompt_engine.api.rest import app
        client = TestClient(app)
        r1 = client.post("/v1/preview", json={"prompt": "hello world", "model": "picsum"})
        r2 = client.post("/v1/preview", json={"prompt": "hello world", "model": "picsum"})
        assert r1.json()["url"] == r2.json()["url"]
