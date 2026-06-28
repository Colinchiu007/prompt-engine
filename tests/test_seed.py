"""Dashboard 种子数据测试"""
from prompt_engine.api.rest import seed_demo_data, get_stats_store
import pytest


@pytest.fixture(autouse=True)
def _seed():
    """每次测试前自动注入种子数据"""
    seed_demo_data(reset_first=True)


class TestSeedData:
    """自动种子填充测试."""

    def test_seed_fills_total_requests(self):
        """seed 后 total_requests 应当大于 0"""
        store = get_stats_store()
        assert store["total_requests"] > 0

    def test_seed_fills_categories(self):
        """seed 后分类分布应有数据"""
        store = get_stats_store()
        assert len(store["categories"]) > 0

    def test_seed_fills_platforms(self):
        """seed 后平台分布应有数据"""
        store = get_stats_store()
        assert len(store["platforms"]) > 0

    def test_seed_double_call_safe(self):
        """多次调用 seed_demo_data() 不会抛异常"""
        seed_demo_data()
        assert True
