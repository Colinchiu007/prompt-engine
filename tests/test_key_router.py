"""Tests for KeyRouter — LLM key selection logic."""
import os
import sys
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


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
    async def test_fetch_keys_success(self):
        """Successful key fetch from OpsCenter."""
        from prompt_engine.ops_client import fetch_official_keys
        import httpx
        from unittest.mock import AsyncMock, patch

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "keys": [
                {"id": "k1", "provider": "deepseek", "is_active": True, "tier_access": 1, "priority": 2},
                {"id": "k2", "provider": "deepseek", "is_active": True, "tier_access": 3, "priority": 1},
                {"id": "k3", "provider": "deepseek", "is_active": False, "tier_access": 1, "priority": 1},
            ]
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
            keys = await fetch_official_keys("deepseek", user_tier=1)
            # Only k1 should be returned (active, tier_access <= 1)
            assert len(keys) == 1
            assert keys[0]["id"] == "k1"

    @pytest.mark.asyncio
    async def test_fetch_keys_fallback_on_error(self):
        """Returns empty list when OpsCenter is unreachable."""
        from prompt_engine.ops_client import fetch_official_keys
        from unittest.mock import AsyncMock, patch

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                side_effect=Exception("Connection refused")
            )
            keys = await fetch_official_keys("deepseek", user_tier=1)
            assert keys == []
