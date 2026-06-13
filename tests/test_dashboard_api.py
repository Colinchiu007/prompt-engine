"""看板统计 API 测试."""
import pytest
from unittest.mock import patch, MagicMock


class TestOverviewStats:
    """P2: 看板概览统计."""

    def test_overview_returns_stats(self):
        from prompt_engine.api.rest import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        resp = client.get("/v1/stats/overview")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_requests" in data
        assert "success_rate" in data
        assert "avg_time_ms" in data

    def test_overview_has_positive_numbers(self):
        from prompt_engine.api.rest import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        resp = client.get("/v1/stats/overview")
        data = resp.json()
        assert data["total_requests"] >= 0
        assert 0 <= data["success_rate"] <= 100


class TestCategoryStats:
    """P2: 分类分布统计."""

    def test_category_distribution(self):
        from prompt_engine.api.rest import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        resp = client.get("/v1/stats/categories")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        if data:
            assert "name" in data[0]
            assert "count" in data[0]


class TestPlatformStats:
    """P2: 平台分布统计."""

    def test_platform_distribution(self):
        from prompt_engine.api.rest import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        resp = client.get("/v1/stats/platforms")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        if data:
            assert "platform" in data[0]
            assert "count" in data[0]