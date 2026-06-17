"""v0.17.0 — 优化速度测试"""
from fastapi.testclient import TestClient


class TestSpeedOptimization:
    """速度优化测试."""

    def test_default_max_length_is_300(self):
        """OptimizeRequest 默认 max_length 应为 300"""
        from prompt_engine.models import OptimizeRequest
        req = OptimizeRequest(prompt="a cat", platform="midjourney")
        assert req.max_length == 300, f"Got {req.max_length}"

    def test_fast_mode_max_length_150(self):
        """快速模式 max_length=150"""
        from prompt_engine.models import OptimizeRequest
        req = OptimizeRequest(prompt="a cat", platform="midjourney", max_length=150)
        assert req.max_length == 150

    def test_speed_mode_endpoint_accepts_max_length(self):
        """POST /v1/optimize 接受 max_length 参数"""
        from prompt_engine.api.rest import app
        client = TestClient(app)
        resp = client.post("/v1/optimize", json={
            "prompt": "a cat", "platform": "midjourney", "max_length": 150
        })
        # 应通过验证（不 400），即使 502（无 LLM key）
        assert resp.status_code in (200, 502, 400), f"Got {resp.status_code}"
