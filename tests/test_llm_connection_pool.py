"""LLM 客户端连接池回归保护测试

背景（QM-5 Bug 复盘）：透明代理（如 OpenWrt OpenClash）中断 keep-alive 长连接时，
OpenAI Python 库默认的 httpx 连接池不会及时 close() 释放 socket，导致 CLOSE_WAIT 泄漏堆积。

修复：OpenAICompatProvider 显式注入有界连接池（httpx.Limits），
限制 max_keepalive_connections + keepalive_expiry，从客户端侧根治连接泄漏。

本测试断言：
  1. provider 客户端使用有界连接池（max_keepalive_connections 有界）
  2. keepalive_expiry 已配置（空闲连接定期过期关闭）
  3. 连接池限制常量存在且数值合理
"""
import httpx

from prompt_engine.llm.openai_compat import OpenAICompatProvider, _CONNECTION_POOL_LIMITS


class TestOpenAICompatConnectionPool:
    """OpenAI 兼容 provider 的有界连接池契约。"""

    def test_connection_pool_limits_are_bounded(self):
        """连接池必须是有界的：max_keepalive_connections 不能为 None（无限）。"""
        assert _CONNECTION_POOL_LIMITS.max_keepalive_connections is not None
        assert _CONNECTION_POOL_LIMITS.max_keepalive_connections >= 1
        assert _CONNECTION_POOL_LIMITS.max_connections is not None
        assert _CONNECTION_POOL_LIMITS.max_connections >= _CONNECTION_POOL_LIMITS.max_keepalive_connections

    def test_keepalive_expiry_is_configured(self):
        """keepalive_expiry 必须配置（默认 5.0），空闲连接定期过期关闭，防止残留。"""
        assert _CONNECTION_POOL_LIMITS.keepalive_expiry is not None
        assert _CONNECTION_POOL_LIMITS.keepalive_expiry > 0

    def test_provider_client_uses_bounded_http_client(self):
        """provider 创建的 OpenAI 客户端必须使用有界 httpx.Client，而非默认无限连接池。"""
        provider = OpenAICompatProvider({
            "api_key": "sk-test-not-secret",
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-4o",
        })
        http_client = provider._client._client  # openai 客户端内部的 httpx.Client
        assert isinstance(http_client, httpx.Client)
        pool = http_client._transport._pool
        assert pool._max_keepalive_connections is not None
        assert pool._max_keepalive_connections >= 1
        assert pool._keepalive_expiry is not None
        assert pool._keepalive_expiry > 0

    def test_provider_created_via_from_llm_object_uses_bounded_pool(self):
        """经 from_llm_object 工厂创建的 provider 同样必须使用有界连接池。"""
        from prompt_engine.llm.base import BaseLLMProvider
        provider = BaseLLMProvider.from_llm_object({
            "provider": "openai_compat",
            "model": "gpt-4o",
            "api_key": "sk-test-not-secret",
            "base_url": "https://api.openai.com/v1",
        })
        assert isinstance(provider, OpenAICompatProvider)
        http_client = provider._client._client
        pool = http_client._transport._pool
        assert pool._max_keepalive_connections is not None
        assert pool._keepalive_expiry is not None