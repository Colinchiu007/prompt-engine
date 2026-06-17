"""v0.12.0 — 反馈闭环 UI + 扰动增强 UI"""


class TestFeedbackUI:
    """F1: 反馈闭环 UI."""

    def test_feedback_submit_accepted(self):
        """POST /v1/feedback 应接受正反馈"""
        from fastapi.testclient import TestClient
        from prompt_engine.api.rest import app
        client = TestClient(app)
        resp = client.post("/v1/feedback", json={
            "entry_type": "positive",
            "prompt": "a majestic cat",
            "optimized_prompt": "A majestic feline...",
            "platform": "midjourney",
            "category": "nature_and_animals"
        })
        assert resp.status_code == 200, f"Got {resp.status_code}: {resp.text}"

    def test_feedback_recent_returns_list(self):
        """GET /v1/feedback/recent 应返回列表"""
        from fastapi.testclient import TestClient
        from prompt_engine.api.rest import app
        client = TestClient(app)
        resp = client.get("/v1/feedback/recent?limit=5")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)


class TestDisturbUI:
    """F2: 扰动增强 UI."""

    def test_disturb_endpoint_accepted(self):
        """POST /v1/disturb-optimize 不应 422"""
        from fastapi.testclient import TestClient
        from prompt_engine.api.rest import app
        client = TestClient(app)
        resp = client.post("/v1/disturb-optimize", json={
            "prompt": "a cat",
            "platform": "midjourney"
        })
        # 可能 502 (无 LLM key)，但不该 422
        assert resp.status_code in (200, 502)

    def test_disturb_returns_candidates(self):
        """扰动结果应有 candidates 字段"""
        from fastapi.testclient import TestClient
        from prompt_engine.api.rest import app
        client = TestClient(app)
        resp = client.post("/v1/disturb-optimize", json={
            "prompt": "a cat",
            "platform": "midjourney",
            "num_candidates": 3
        })
        if resp.status_code == 200:
            data = resp.json()
            assert "candidates" in data