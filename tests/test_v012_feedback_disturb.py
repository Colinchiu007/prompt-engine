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

    def test_disturb_endpoint_requires_caller_llm(self):
        """默认 LLM 路径缺少调用方绑定时 fail-closed 返回 422。"""
        from fastapi.testclient import TestClient
        from prompt_engine.api.rest import app
        client = TestClient(app)
        resp = client.post("/v1/disturb-optimize", json={
            "prompt": "a cat",
            "platform": "midjourney"
        })
        assert resp.status_code == 422
        assert "llm 必填" in resp.json()["detail"]

    def test_disturb_returns_422_without_caller_llm(self):
        """默认 LLM 路径没有调用方绑定时不进入扰动执行。"""
        from fastapi.testclient import TestClient
        from prompt_engine.api.rest import app
        client = TestClient(app)
        resp = client.post("/v1/disturb-optimize", json={
            "prompt": "a cat",
            "platform": "midjourney",
            "num_candidates": 3
        })
        assert resp.status_code == 422
        assert "llm 必填" in resp.json()["detail"]

    def test_disturb_template_strategy_does_not_require_llm(self):
        """显式模板策略仍可在无 LLM 绑定时执行。"""
        from fastapi.testclient import TestClient
        from prompt_engine.api.rest import app
        client = TestClient(app)
        resp = client.post("/v1/disturb-optimize", json={
            "prompt": "a cat",
            "platform": "midjourney",
            "creative_level": 10,
            "optimization_strategy": "template",
        })
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["strategy_used"] == "template"
        assert data["key_source"] == "none"
