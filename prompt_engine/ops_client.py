"""OpsCenter API client — fetch official keys for LLM routing."""
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Default OpsCenter URL (ECS internal)
OPS_CENTER_URL = os.environ.get("OPS_CENTER_URL", "http://127.0.0.1:8010")


async def fetch_official_keys(
    provider: str,
    user_tier: int,
    ops_url: Optional[str] = None,
) -> list[dict]:
    """Fetch active official keys for a provider, filtered by user tier.

    Returns list of keys sorted by priority (lowest = best).
    Each key: {id, provider, name, api_key (masked), base_url, models, priority, tier_access, ...}

    Falls back to empty list if OpsCenter is unreachable.
    """
    import httpx
    url = f"{ops_url or OPS_CENTER_URL}/api/v1/secrets"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url, params={"provider": provider})
            if resp.status_code == 200:
                keys = resp.json().get("keys", [])
                # Filter by tier_access <= user_tier and is_active
                active = [k for k in keys if k.get("is_active") and k.get("tier_access", 1) <= user_tier]
                active.sort(key=lambda k: k.get("priority", 99))
                return active
    except Exception as e:
        logger.warning(f"OpsCenter unreachable, using fallback keys: {e}")
    return []


async def reveal_key(key_id: str, ops_url: Optional[str] = None) -> Optional[str]:
    """Reveal the plaintext of an official key (requires admin auth — for service use).

    Falls back to returning None if OpsCenter is unreachable.
    """
    import httpx
    import jwt
    import datetime

    # Generate a service-to-service JWT
    secret = os.environ.get("PO_SECRET_KEY", os.environ.get("OPS_SECRET_KEY", "fallback"))
    token = jwt.encode({
        "user_id": "prompt-engine",
        "username": "prompt-engine",
        "role": "admin",
        "exp": datetime.datetime.utcnow() + datetime.timedelta(minutes=5),
    }, secret, algorithm="HS256")

    url = f"{ops_url or OPS_CENTER_URL}/api/v1/secrets/{key_id}/reveal"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(url, headers={"Authorization": f"Bearer {token}"})
            if resp.status_code == 200:
                return resp.json().get("api_key")
    except Exception as e:
        logger.warning(f"Failed to reveal key {key_id}: {e}")
    return None
