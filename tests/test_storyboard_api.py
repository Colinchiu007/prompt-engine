"""Tests for storyboard REST API endpoints"""
import pytest
from fastapi.testclient import TestClient


class TestStoryboardListStrategies:
    """GET /v1/storyboard/strategies"""

    def test_list_returns_200(self):
        """列出策略返回 200"""
        from prompt_engine.api.rest import app
        client = TestClient(app)
        resp = client.get("/v1/storyboard/strategies")
        assert resp.status_code == 200
        data = resp.json()
        assert "strategies" in data
        assert "count" in data

    def test_list_contains_xiaohei(self):
        """列表中包含 xiaohei_storyboard"""
        from prompt_engine.api.rest import app
        client = TestClient(app)
        resp = client.get("/v1/storyboard/strategies")
        data = resp.json()
        names = [s["name"] for s in data["strategies"]]
        assert "xiaohei_storyboard" in names

    def test_list_includes_display_name(self):
        """每个策略含 display_name 和 description"""
        from prompt_engine.api.rest import app
        client = TestClient(app)
        resp = client.get("/v1/storyboard/strategies")
        data = resp.json()
        for s in data["strategies"]:
            assert "display_name" in s
            assert "description" in s
            assert len(s["display_name"]) > 0

    def test_list_count_matches(self):
        """count 字段应与 strategies 长度一致"""
        from prompt_engine.api.rest import app
        client = TestClient(app)
        resp = client.get("/v1/storyboard/strategies")
        data = resp.json()
        assert data["count"] == len(data["strategies"])


class TestStoryboardCompose:
    """POST /v1/storyboard/compose"""

    def test_compose_basic(self):
        """基本合成返回 prompts 和 metaphors"""
        from prompt_engine.api.rest import app
        client = TestClient(app)
        resp = client.post("/v1/storyboard/compose", json={
            "scenes": ["市场竞争", "技术迭代"],
            "full_text": "在激烈的市场竞争中不断进行技术迭代",
        })
        assert resp.status_code == 200, f"Got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "strategy" in data
        assert data["strategy"] == "xiaohei_storyboard"
        assert "prompts" in data
        assert len(data["prompts"]) == 2
        assert "metaphors" in data
        assert len(data["metaphors"]) == 2
        # 验证每个 prompt 非空
        for p in data["prompts"]:
            assert isinstance(p, str)
            assert len(p) > 50
        # 验证每个 metaphor 包含必要字段
        for m in data["metaphors"]:
            assert "composition_type" in m

    def test_compose_single_scene(self):
        """单场景合成"""
        from prompt_engine.api.rest import app
        client = TestClient(app)
        resp = client.post("/v1/storyboard/compose", json={
            "scenes": ["AI 改变教育"],
            "full_text": "AI 改变教育",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["prompts"]) == 1

    def test_compose_empty_scenes_400(self):
        """空 scenes 返回 400"""
        from prompt_engine.api.rest import app
        client = TestClient(app)
        resp = client.post("/v1/storyboard/compose", json={
            "scenes": [],
            "full_text": "",
        })
        assert resp.status_code == 400

    def test_compose_unknown_strategy_404(self):
        """未知 strategy 返回 404"""
        from prompt_engine.api.rest import app
        client = TestClient(app)
        resp = client.post("/v1/storyboard/compose", json={
            "scenes": ["测试"],
            "full_text": "测试",
            "strategy": "nonexistent_strategy",
        })
        assert resp.status_code == 404

    def test_compose_with_options(self):
        """带 options 参数合成"""
        from prompt_engine.api.rest import app
        client = TestClient(app)
        resp = client.post("/v1/storyboard/compose", json={
            "scenes": ["平衡"],
            "full_text": "寻找平衡",
            "strategy": "xiaohei_storyboard",
            "options": {"creative_level": 7, "composition_type": "概念隐喻"},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["prompts"]) == 1

    def test_compose_long_text(self):
        """长文本合成不崩溃"""
        from prompt_engine.api.rest import app
        client = TestClient(app)
        long_scene = "技术" * 1000
        resp = client.post("/v1/storyboard/compose", json={
            "scenes": [long_scene],
            "full_text": long_scene,
        })
        assert resp.status_code == 200

    def test_compose_no_scenes_key_400(self):
        """缺少 scenes 键应返回 400"""
        from prompt_engine.api.rest import app
        client = TestClient(app)
        resp = client.post("/v1/storyboard/compose", json={
            "full_text": "测试",
        })
        assert resp.status_code == 400

    def test_compose_strategy_format(self):
        """返回的策略名含具体信息"""
        from prompt_engine.api.rest import app
        client = TestClient(app)
        resp = client.post("/v1/storyboard/compose", json={
            "scenes": ["测试"],
            "full_text": "测试",
        })
        data = resp.json()
        assert isinstance(data["strategy"], str)
        assert len(data["strategy"]) > 0

    def test_compose_response_no_internal_error(self):
        """错误响应不应包含内部路径"""
        from prompt_engine.api.rest import app
        client = TestClient(app)
        resp = client.post("/v1/storyboard/compose", json={
            "scenes": [],
            "full_text": "",
        })
        body = resp.text.lower()
        assert "traceback" not in body
        assert "file" not in body
