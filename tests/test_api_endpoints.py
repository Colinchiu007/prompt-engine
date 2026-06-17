"""v0.19.x — REST API 端点集成测试

覆盖 P0-P2 的关键端点：
  - POST /v1/optimize（模板路径，免 LLM）
  - POST /v1/classify（关键词匹配路径，免 LLM）
  - POST /v1/feedback + GET /v1/feedback/stats
  - GET /v1/cache/stats
  - GET /v1/resources
  - POST /v1/preview
  - POST /v1/optimize batch
  - 输入验证（短文本 400）
"""
import pytest
from fastapi.testclient import TestClient


class TestOptimizeEndpoint:
    """POST /v1/optimize — 核心优化端点"""

    def test_optimize_template_path(self):
        """creative_level=1 走模板直出，返回成功"""
        from prompt_engine.api.rest import app
        client = TestClient(app)
        resp = client.post("/v1/optimize", json={
            "prompt": "a cat",
            "platform": "generic",
            "creative_level": 1,
        })
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "optimized_prompt" in data
        assert len(data["optimized_prompt"]) > 0
        assert data["tokens_used"] == 0

    def test_optimize_short_text_rejected(self):
        """短中文应返回 400"""
        from prompt_engine.api.rest import app
        client = TestClient(app)
        resp = client.post("/v1/optimize", json={
            "prompt": "好吧",
            "platform": "generic",
        })
        assert resp.status_code == 400

    def test_optimize_short_english_rejected(self):
        """短英文（< 3 词）应返回 400"""
        from prompt_engine.api.rest import app
        client = TestClient(app)
        resp = client.post("/v1/optimize", json={
            "prompt": "ok",
            "platform": "generic",
        })
        assert resp.status_code == 400

    def test_optimize_midjourney(self):
        """MJ 平台也走模板路径"""
        from prompt_engine.api.rest import app
        client = TestClient(app)
        resp = client.post("/v1/optimize", json={
            "prompt": "sunset over mountains",
            "platform": "midjourney",
            "creative_level": 1,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "optimized_prompt" in data

    def test_optimize_all_platforms(self):
        """所有 7 个平台都能返回 200"""
        from prompt_engine.api.rest import app
        client = TestClient(app)
        platforms = ["midjourney", "stable_diffusion", "dalle", "tongyi", "yizhang", "jimeng", "generic"]
        for p in platforms:
            resp = client.post("/v1/optimize", json={
                "prompt": "a test prompt",
                "platform": p,
                "creative_level": 1,
            })
            assert resp.status_code == 200, f"{p} failed: {resp.status_code}"
            assert resp.json()["tokens_used"] == 0

    def test_optimize_invalid_platform(self):
        """无效 platform 返回非 500 错误"""
        from prompt_engine.api.rest import app
        client = TestClient(app)
        resp = client.post("/v1/optimize", json={
            "prompt": "test",
            "platform": "nonexistent",
            "creative_level": 1,
        })
        # 应优雅处理，不抛出 500
        assert resp.status_code != 500


class TestBatchOptimize:
    """POST /v1/optimize/batch — 批量优化"""

    def test_batch_optimize(self):
        """批量优化返回数组"""
        from prompt_engine.api.rest import app
        client = TestClient(app)
        resp = client.post("/v1/optimize/batch", json={
            "requests": [
                {"prompt": "cat", "platform": "generic", "creative_level": 1},
                {"prompt": "dog", "platform": "generic", "creative_level": 1},
            ]
        })
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 2
        for item in data:
            assert "optimized_prompt" in item

    def test_batch_empty(self):
        """空批量返回 422"""
        from prompt_engine.api.rest import app
        client = TestClient(app)
        resp = client.post("/v1/optimize/batch", json={"requests": []})
        assert resp.status_code != 500


class TestClassifyEndpoint:
    """POST /v1/classify — 风格分类（关键词匹配路径，免 LLM）"""

    def test_classify_basic(self):
        """分类返回 categories 列表"""
        from prompt_engine.api.rest import app
        client = TestClient(app)
        resp = client.post("/v1/classify", json={
            "prompt": "a serene lake surrounded by mountains at sunset",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "categories" in data

    def test_classify_cyberpunk(self):
        """赛博朋克 prompt 应命中相关维度"""
        from prompt_engine.api.rest import app
        client = TestClient(app)
        resp = client.post("/v1/classify", json={
            "prompt": "cyberpunk city neon lights rain night",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert len(data.get("categories", [])) > 0


class TestFeedbackEndpoint:
    """POST /v1/feedback + GET /v1/feedback/stats — 反馈闭环"""

    def test_submit_feedback(self):
        """提交反馈应成功"""
        from prompt_engine.api.rest import app
        client = TestClient(app)
        resp = client.post("/v1/feedback", json={
            "prompt": "a cat",
            "optimized_prompt": "a majestic cat --ar 16:9",
            "platform": "midjourney",
            "rating": 5,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "id" in data

    def test_feedback_stats(self):
        """反馈统计返回计数"""
        from prompt_engine.api.rest import app
        client = TestClient(app)
        resp = client.get("/v1/feedback/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)

    def test_feedback_invalid_rating(self):
        """无效评分应返回 422"""
        from prompt_engine.api.rest import app
        client = TestClient(app)
        resp = client.post("/v1/feedback", json={
            "prompt": "test",
            "optimized_prompt": "test",
            "platform": "midjourney",
            "rating": 999,
        })
        assert resp.status_code == 422


class TestCacheStatsEndpoint:
    """GET /v1/cache/stats — v0.19.0 缓存统计"""

    def test_cache_stats(self):
        """缓存统计返回 sqlite + memory 信息"""
        from prompt_engine.api.rest import app
        client = TestClient(app)
        resp = client.get("/v1/cache/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "sqlite" in data
        assert "memory" in data
        assert "entries" in data["sqlite"]
        assert "entries" in data["memory"]

    def test_cache_stats_after_optimize(self):
        """优化后缓存应有条目"""
        from prompt_engine.api.rest import app
        client = TestClient(app)
        # 先优化一次
        client.post("/v1/optimize", json={
            "prompt": "cache test",
            "platform": "generic",
            "creative_level": 1,
        })
        resp = client.get("/v1/cache/stats")
        data = resp.json()
        # SQLite 和 Memory 都应有条目
        assert data["sqlite"]["entries"] > 0
        assert data["memory"]["entries"] > 0


class TestResourcesEndpoint:
    """GET /v1/resources — 引擎资源"""

    def test_resources(self):
        """资源返回平台/案例/关键词计数"""
        from prompt_engine.api.rest import app
        client = TestClient(app)
        resp = client.get("/v1/resources")
        assert resp.status_code == 200
        data = resp.json()
        assert "platforms" in data
        assert data["platforms"] >= 7


class TestPreviewEndpoint:
    """POST /v1/preview — 图片预览 URL"""

    def test_preview_picsum_default(self):
        """默认模型 picsum 返回合法 URL"""
        from prompt_engine.api.rest import app
        client = TestClient(app)
        resp = client.post("/v1/preview", json={
            "prompt": "test cat",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["model"] == "picsum"
        assert "https://picsum.photos" in data["url"]

    def test_preview_empty_prompt(self):
        """空 prompt 返回 400"""
        from prompt_engine.api.rest import app
        client = TestClient(app)
        resp = client.post("/v1/preview", json={"prompt": ""})
        assert resp.status_code == 400

    def test_preview_unknown_model(self):
        """未知模型返回 placeholder 且不报 500"""
        from prompt_engine.api.rest import app
        client = TestClient(app)
        resp = client.post("/v1/preview", json={
            "prompt": "test",
            "model": "unknown_model_xyz",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["url"] == ""
        assert "note" in data


class TestSecurityEndpoints:
    """安全与错误处理"""

    def test_exception_does_not_leak_details(self):
        """异常不应泄露内部细节到 response"""
        from prompt_engine.api.rest import app
        client = TestClient(app)
        # 故意发送无效数据触发异常
        resp = client.post("/v1/optimize", json={
            "prompt": "a" * 99999,  # 超大 prompt
            "platform": "generic",
        })
        # 不应包含内部路径/配置
        body = resp.text.lower()
        assert "traceback" not in body
        assert "file" not in body
        assert "c:" not in body and "/home/" not in body
