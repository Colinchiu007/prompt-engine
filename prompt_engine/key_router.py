"""LLM Key Router — selects the best API key for a given user tier and provider.

Priority:
  1. User's own API key (if provided in request)
  2. Best official key from OpsCenter (by priority, filtered by tier)
  3. Fallback: config.yaml / env var key
"""
import os
import logging
from typing import Optional

from prompt_engine.llm.base import BaseLLMProvider
from prompt_engine.ops_client import fetch_official_keys, reveal_key
from prompt_engine.config import load_config

logger = logging.getLogger(__name__)


class KeyRouter:
    """Routes LLM requests to the appropriate API key and provider.

    Usage:
        router = KeyRouter()
        provider = await router.get_provider("openai", user_tier=2, user_own_key="sk-xxx")
        result = provider.chat(messages)
    """

    def __init__(self, ops_url: Optional[str] = None):
        self.ops_url = ops_url
        self._config = None
        self._key_cache: dict[str, str] = {}  # key_id -> plaintext (short-lived)

    def _load_config(self):
        if self._config is None:
            try:
                self._config = load_config()
            except Exception:
                self._config = {}

    def _get_fallback_key(self, provider: str) -> Optional[str]:
        """Get API key from local config.yaml / env var as last resort."""
        self._load_config()
        llm_cfg = self._config.get("llm", {})

        # Try the specific provider config
        provider_cfg = llm_cfg.get(provider, {})
        key = provider_cfg.get("api_key", "")
        if key and not key.startswith("${"):
            return key

        # Try env var directly
        env_map = {
            "openai": "OPENAI_API_KEY",
            "deepseek": "DEEPSEEK_API_KEY",
            "minimax": "MINIMAX_API_KEY",
            "xfyun": "XFYUN_API_KEY",
            "doubao": "DOUBAO_API_KEY",
        }
        env_var = env_map.get(provider)
        if env_var:
            return os.environ.get(env_var)

        return None

    async def get_provider(
        self,
        provider: str,
        user_tier: int = 1,
        user_own_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> BaseLLMProvider:
        """Get the best LLM provider for the given parameters.

        Args:
            provider: Provider name (openai, deepseek, minimax, etc.)
            user_tier: User's membership tier (1=free, 2=standard, 3=pro)
            user_own_key: User's own API key (if configured in settings)
            model: Override model (otherwise from config)
            base_url: Override base URL
        """
        api_key = None
        selected_base_url = base_url
        selected_model = model
        key_source = "fallback"

        # Priority 1: User's own key
        if user_own_key:
            api_key = user_own_key
            key_source = "user"
            logger.info(f"Using user's own key for {provider}")

        # Priority 2: Best official key from OpsCenter
        if not api_key:
            official_keys = await fetch_official_keys(provider, user_tier, self.ops_url)
            if official_keys:
                best = official_keys[0]  # Already sorted by priority
                key_id = best["id"]
                # Check cache first
                if key_id in self._key_cache:
                    api_key = self._key_cache[key_id]
                else:
                    api_key = await reveal_key(key_id, self.ops_url)
                    if api_key:
                        self._key_cache[key_id] = api_key  # Cache for session

                if api_key:
                    key_source = f"official:{key_id}"
                    # Use official key's configured base URL and model if not overridden
                    if not selected_base_url:
                        selected_base_url = best.get("base_url") or None
                    if not selected_model and best.get("models"):
                        models = best["models"]
                        selected_model = models[0] if isinstance(models, list) and models else models
                    logger.info(f"Using official key {key_id} (tier={best.get('tier_access')}) for {provider}")

        # Priority 3: Fallback to local config
        if not api_key:
            api_key = self._get_fallback_key(provider)
            key_source = "config"
            if api_key:
                logger.info(f"Using config.yaml fallback key for {provider}")
            else:
                logger.error(f"No key available for provider={provider}, tier={user_tier}")

        if not api_key:
            raise ValueError(f"No API key available for provider '{provider}' at tier {user_tier}")

        # Resolve model and base_url from config if not set
        if not selected_model or not selected_base_url:
            self._load_config()
            llm_cfg = self._config.get("llm", {})
            provider_cfg = llm_cfg.get(provider, {})
            if not selected_model:
                selected_model = provider_cfg.get("model", "")
            if not selected_base_url:
                selected_base_url = provider_cfg.get("base_url", "")

        # Create provider
        provider_instance = BaseLLMProvider.from_config({
            "llm": {
                "provider": provider,
                provider: {
                    "api_key": api_key,
                    "base_url": selected_base_url or "",
                    "model": selected_model or "",
                }
            }
        })
        # Attach metadata
        provider_instance._key_source = key_source
        return provider_instance

    def clear_cache(self):
        """Clear the key cache (call periodically to refresh keys)."""
        self._key_cache.clear()
