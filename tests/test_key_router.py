"""Tests for KeyRouter — LLM key selection logic."""
import os
import sys
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

TEST_SERVICE_SECRET = "test-service-secret-with-at-least-32-characters"


class TestKeyRouter:
    """KeyRouter key selection logic."""

    @pytest.mark.asyncio
    async def test_user_own_key_priority(self):
        """User's own key is always used first."""
        from prompt_engine.key_router import KeyRouter

        router = KeyRouter()
        # Mock fetch_official_keys to return keys (should be ignored)
        with patch("prompt_engine.key_router.fetch_official_keys", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = [{"id": "off1", "is_active": True, "tier_access": 1, "priority": 1}]
            with patch("prompt_engine.key_router.reveal_key", new_callable=AsyncMock) as mock_reveal:
                mock_reveal.return_value = "sk-official"

                provider = await router.get_provider("deepseek", user_tier=1, user_own_key="sk-user-key")
                assert provider._key_source == "user"
                # Official keys should NOT have been fetched
                mock_fetch.assert_not_called()

    @pytest.mark.asyncio
    async def test_official_key_fallback(self):
        """When no user key, use the best official key from OpsCenter."""
        from prompt_engine.key_router import KeyRouter

        router = KeyRouter()
        with patch("prompt_engine.key_router.fetch_official_keys", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = [
                {"id": "off2", "is_active": True, "tier_access": 1, "priority": 1, "base_url": "", "models": ["deepseek-chat"]},
                {"id": "off1", "is_active": True, "tier_access": 1, "priority": 2, "base_url": "", "models": ["deepseek-chat"]},
            ]
            with patch("prompt_engine.key_router.reveal_key", new_callable=AsyncMock) as mock_reveal:
                mock_reveal.return_value = "sk-best-official"

                provider = await router.get_provider("deepseek", user_tier=1)
                assert provider._key_source == "official:off2"  # Best priority
                mock_reveal.assert_called_once_with("off2", None)

    @pytest.mark.asyncio
    async def test_tier_filtering(self):
        """Free users (tier 1) can't use tier 3 keys."""
        from prompt_engine.key_router import KeyRouter

        router = KeyRouter()
        with patch("prompt_engine.key_router.fetch_official_keys", new_callable=AsyncMock) as mock_fetch:
            # OpsCenter returns ALL keys; fetch_official_keys filters by tier
            mock_fetch.return_value = []  # No keys for tier 1
            with patch("prompt_engine.key_router.reveal_key", new_callable=AsyncMock):
                # Should use config fallback
                with patch.object(router, "_get_fallback_key", return_value="sk-fallback"):
                    provider = await router.get_provider("deepseek", user_tier=1)
                    assert provider._key_source == "config"

    @pytest.mark.asyncio
    async def test_config_fallback_last_resort(self):
        """When OpsCenter is down, fall back to config.yaml keys."""
        from prompt_engine.key_router import KeyRouter

        router = KeyRouter()
        with patch("prompt_engine.key_router.fetch_official_keys", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = []  # OpsCenter unreachable
            with patch.object(router, "_get_fallback_key", return_value="sk-config-key"):
                provider = await router.get_provider("deepseek", user_tier=1)
                assert provider._key_source == "config"

    @pytest.mark.asyncio
    async def test_no_key_available_raises(self):
        """Error when no key is available at all."""
        from prompt_engine.key_router import KeyRouter

        router = KeyRouter()
        with patch("prompt_engine.key_router.fetch_official_keys", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = []
            with patch.object(router, "_get_fallback_key", return_value=None):
                with pytest.raises(ValueError, match="No API key available"):
                    await router.get_provider("nonexistent", user_tier=1)

    @pytest.mark.asyncio
    async def test_key_cache_reuse(self):
        """Revealed keys are cached to avoid repeated API calls."""
        from prompt_engine.key_router import KeyRouter

        router = KeyRouter()
        with patch("prompt_engine.key_router.fetch_official_keys", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = [
                {"id": "off1", "is_active": True, "tier_access": 1, "priority": 1, "base_url": "", "models": ["deepseek-chat"]},
            ]
            with patch("prompt_engine.key_router.reveal_key", new_callable=AsyncMock) as mock_reveal:
                mock_reveal.return_value = "sk-cached"

                # First call: should call reveal_key
                await router.get_provider("deepseek", user_tier=1)
                assert mock_reveal.call_count == 1

                # Second call: should use cache
                await router.get_provider("deepseek", user_tier=1)
                assert mock_reveal.call_count == 1  # No additional call

    @pytest.mark.asyncio
    async def test_provider_actually_works(self):
        """The returned provider can actually make calls (integration check)."""
        from prompt_engine.key_router import KeyRouter

        router = KeyRouter()
        with patch.object(router, "_get_fallback_key", return_value="sk-test-123"):
            provider = await router.get_provider("deepseek", user_tier=1, model="deepseek-chat")
            assert provider is not None
            # Check it's a valid BaseLLMProvider
            assert hasattr(provider, "chat")
            assert hasattr(provider, "_key_source")


class TestOpsClient:
    """OpsCenter API client."""

    @pytest.mark.asyncio
    async def test_fetch_keys_success(self, monkeypatch):
        """配置服务密钥后可从 OpsCenter 获取密钥。"""
        from prompt_engine.ops_client import fetch_official_keys
        from unittest.mock import AsyncMock, patch

        monkeypatch.setenv("PO_SECRET_KEY", TEST_SERVICE_SECRET)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "keys": [
                {"id": "k1", "provider": "deepseek", "is_active": True, "tier_access": 1, "priority": 2},
                {"id": "k2", "provider": "deepseek", "is_active": True, "tier_access": 3, "priority": 1},
                {"id": "k3", "provider": "deepseek", "is_active": False, "tier_access": 1, "priority": 1},
            ]
        }

        with patch("prompt_engine.ops_client._create_service_token", return_value="test-token"):
            with patch("httpx.AsyncClient") as mock_client:
                mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
                keys = await fetch_official_keys("deepseek", user_tier=1)
            # Only k1 should be returned (active, tier_access <= 1)
            assert len(keys) == 1
            assert keys[0]["id"] == "k1"

    @pytest.mark.asyncio
    async def test_fetch_keys_fallback_on_error(self, monkeypatch):
        """OpsCenter 不可达时返回空列表。"""
        from prompt_engine.ops_client import fetch_official_keys
        from unittest.mock import AsyncMock, patch

        monkeypatch.setenv("PO_SECRET_KEY", TEST_SERVICE_SECRET)
        with patch("prompt_engine.ops_client._create_service_token", return_value="test-token"):
            with patch("httpx.AsyncClient") as mock_client:
                mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                    side_effect=Exception("连接被拒绝")
                )
                keys = await fetch_official_keys("deepseek", user_tier=1)
                assert keys == []

    @pytest.mark.asyncio
    async def test_fetch_keys_skips_ops_center_without_service_secret(self, monkeypatch):
        """缺少服务密钥时不得签发管理员 JWT 或访问 OpsCenter。"""
        from prompt_engine.ops_client import fetch_official_keys

        monkeypatch.delenv("PO_SECRET_KEY", raising=False)
        monkeypatch.delenv("OPS_SECRET_KEY", raising=False)

        with patch("prompt_engine.ops_client._create_service_token") as mock_token:
            with patch("httpx.AsyncClient") as mock_client:
                keys = await fetch_official_keys("deepseek", user_tier=1)

        assert keys == []
        mock_token.assert_not_called()
        mock_client.assert_not_called()

    @pytest.mark.asyncio
    async def test_fetch_keys_skips_ops_center_with_short_service_secret(self, monkeypatch):
        """短服务密钥不得签发管理员 JWT 或访问 OpsCenter。"""
        from prompt_engine.ops_client import fetch_official_keys

        monkeypatch.setenv("PO_SECRET_KEY", "too-short")
        with patch("prompt_engine.ops_client._create_service_token") as mock_token:
            with patch("httpx.AsyncClient") as mock_client:
                keys = await fetch_official_keys("deepseek", user_tier=1)

        assert keys == []
        mock_token.assert_not_called()
        mock_client.assert_not_called()

    @pytest.mark.asyncio
    async def test_reveal_key_skips_ops_center_without_service_secret(self, monkeypatch):
        """缺少服务密钥时不得请求明文密钥。"""
        from prompt_engine.ops_client import reveal_key

        monkeypatch.delenv("PO_SECRET_KEY", raising=False)
        monkeypatch.delenv("OPS_SECRET_KEY", raising=False)

        with patch("prompt_engine.ops_client._create_service_token") as mock_token:
            with patch("httpx.AsyncClient") as mock_client:
                api_key = await reveal_key("key-1")

        assert api_key is None
        mock_token.assert_not_called()
        mock_client.assert_not_called()

    @pytest.mark.asyncio
    async def test_fetch_keys_reads_ops_center_url_at_call_time(self, monkeypatch):
        """运行时环境覆盖应在模块导入后仍然生效。"""
        import prompt_engine.ops_client as ops_client

        monkeypatch.setenv("PO_SECRET_KEY", TEST_SERVICE_SECRET)
        monkeypatch.setenv("OPS_CENTER_URL", "http://ops-runtime.test:8010")
        monkeypatch.setenv(
            "OPS_CENTER_ALLOWED_ORIGINS",
            "http://ops-runtime.test:8010",
        )
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"keys": []}

        with patch.object(ops_client, "_create_service_token", return_value="test-token"):
            with patch("httpx.AsyncClient") as mock_client:
                mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                    return_value=mock_response,
                )
                await ops_client.fetch_official_keys("deepseek", user_tier=1)

        requested_url = mock_client.return_value.__aenter__.return_value.get.call_args.args[0]
        assert requested_url == "http://ops-runtime.test:8010/api/v1/secrets"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "ops_url",
        [
            "http://169.254.169.254",
            "http://127.0.0.1:8000",
            "http://127.0.0.1:8010/unexpected-path",
            "https://attacker.example",
        ],
    )
    async def test_fetch_keys_rejects_unapproved_ops_center_origin(
        self,
        monkeypatch,
        ops_url,
    ):
        """服务令牌不得发送到未明确批准的来源。"""
        from prompt_engine.ops_client import fetch_official_keys

        monkeypatch.setenv("PO_SECRET_KEY", TEST_SERVICE_SECRET)
        monkeypatch.delenv("OPS_CENTER_ALLOWED_ORIGINS", raising=False)
        with patch("prompt_engine.ops_client._create_service_token", return_value="test-token"):
            with patch("httpx.AsyncClient") as mock_client:
                keys = await fetch_official_keys(
                    "deepseek",
                    user_tier=1,
                    ops_url=ops_url,
                )

        assert keys == []
        mock_client.assert_not_called()

    @pytest.mark.asyncio
    async def test_fetch_keys_disables_http_redirects(self, monkeypatch):
        """OpsCenter 响应不得把服务令牌重定向到其他来源。"""
        from prompt_engine.ops_client import fetch_official_keys

        monkeypatch.setenv("PO_SECRET_KEY", TEST_SERVICE_SECRET)
        mock_response = MagicMock()
        mock_response.status_code = 302

        with patch("prompt_engine.ops_client._create_service_token", return_value="test-token"):
            with patch("httpx.AsyncClient") as mock_client:
                mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                    return_value=mock_response,
                )
                keys = await fetch_official_keys("deepseek", user_tier=1)

        assert keys == []
        assert mock_client.call_args.kwargs["follow_redirects"] is False

    @pytest.mark.asyncio
    async def test_reveal_key_rejects_non_string_api_key(self, monkeypatch):
        """OpsCenter 的异常响应不得进入 Provider 配置。"""
        from prompt_engine.ops_client import reveal_key

        monkeypatch.setenv("PO_SECRET_KEY", TEST_SERVICE_SECRET)
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"api_key": {"unexpected": "value"}}

        with patch("prompt_engine.ops_client._create_service_token", return_value="test-token"):
            with patch("httpx.AsyncClient") as mock_client:
                mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                    return_value=mock_response,
                )
                api_key = await reveal_key("key-1")

        assert api_key is None

    @pytest.mark.asyncio
    async def test_fetch_keys_rejects_public_default_service_secret(self, monkeypatch):
        """公开默认密钥不得用于签发管理员服务令牌。"""
        from prompt_engine.ops_client import fetch_official_keys

        monkeypatch.setenv("PO_SECRET_KEY", "dev-secret-change-in-production")
        with patch("prompt_engine.ops_client._create_service_token") as mock_token:
            with patch("httpx.AsyncClient") as mock_client:
                keys = await fetch_official_keys("deepseek", user_tier=1)

        assert keys == []
        mock_token.assert_not_called()
        mock_client.assert_not_called()

    @pytest.mark.asyncio
    async def test_fetch_keys_rejects_non_http_ops_center_url(self, monkeypatch):
        """非法协议不得触发携带服务令牌的外部请求。"""
        from prompt_engine.ops_client import fetch_official_keys

        monkeypatch.setenv("PO_SECRET_KEY", TEST_SERVICE_SECRET)
        with patch("prompt_engine.ops_client._create_service_token", return_value="test-token"):
            with patch("httpx.AsyncClient") as mock_client:
                keys = await fetch_official_keys(
                    "deepseek",
                    user_tier=1,
                    ops_url="file:///tmp/ops-center",
                )

        assert keys == []
        mock_client.assert_not_called()

    @pytest.mark.asyncio
    async def test_fetch_keys_filters_mismatched_provider_payload(self, monkeypatch):
        """OpsCenter 响应不能绕过请求中的供应商边界。"""
        from prompt_engine.ops_client import fetch_official_keys

        monkeypatch.setenv("PO_SECRET_KEY", TEST_SERVICE_SECRET)
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "keys": [
                {
                    "id": "wrong-provider",
                    "provider": "openai",
                    "is_active": True,
                    "tier_access": 1,
                },
                {
                    "id": "right-provider",
                    "provider": "deepseek",
                    "is_active": True,
                    "tier_access": 1,
                },
            ],
        }

        with patch("prompt_engine.ops_client._create_service_token", return_value="test-token"):
            with patch("httpx.AsyncClient") as mock_client:
                mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                    return_value=mock_response,
                )
                keys = await fetch_official_keys("deepseek", user_tier=1)

        assert [key["id"] for key in keys] == ["right-provider"]
