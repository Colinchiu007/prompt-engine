"""OpsCenter API client — fetch official keys for LLM routing."""
import os
import logging
from typing import Optional
from urllib.parse import quote, urlsplit

logger = logging.getLogger(__name__)

DEFAULT_OPS_CENTER_URL = "http://127.0.0.1:8010"
DEFAULT_ALLOWED_ORIGINS = frozenset(
    {
        "http://127.0.0.1:8010",
        "http://localhost:8010",
        "http://[::1]:8010",
    }
)
JWT_ALGORITHM = "HS256"
INSECURE_DEFAULT_SECRET = "dev-secret-change-in-production"
MIN_SERVICE_SECRET_LENGTH = 32


def _normalized_origin(value: str) -> str:
    """返回精确到协议、主机和端口的规范化来源。"""
    parsed = urlsplit(value)
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("OpsCenter 地址端口无效") from exc

    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise ValueError(
            "OpsCenter 地址必须是无路径、凭证、查询参数和片段的 HTTP(S) 来源"
        )

    host = parsed.hostname.rstrip(".").lower()
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ValueError("OpsCenter 地址主机名无效") from exc

    normalized_port = port or (443 if parsed.scheme == "https" else 80)
    if not 1 <= normalized_port <= 65535:
        raise ValueError("OpsCenter 地址端口无效")
    rendered_host = f"[{host}]" if ":" in host else host
    return f"{parsed.scheme}://{rendered_host}:{normalized_port}"


def _allowed_origins() -> set[str]:
    """读取额外允许的 OpsCenter 来源；条目必须是不带路径的来源。"""
    allowed = set(DEFAULT_ALLOWED_ORIGINS)
    configured = os.environ.get("OPS_CENTER_ALLOWED_ORIGINS", "")
    for entry in configured.split(","):
        value = entry.strip().rstrip("/")
        if not value:
            continue
        parsed = urlsplit(value)
        if parsed.path not in {"", "/"}:
            raise ValueError("OPS_CENTER_ALLOWED_ORIGINS 只能包含不带路径的来源")
        allowed.add(_normalized_origin(value))
    return allowed


def _ops_center_url(explicit_url: Optional[str]) -> str:
    """读取并校验 OpsCenter HTTP(S) 基础地址。"""
    value = (
        explicit_url
        or os.environ.get("OPS_CENTER_URL")
        or DEFAULT_OPS_CENTER_URL
    ).strip().rstrip("/")
    origin = _normalized_origin(value)
    if origin not in _allowed_origins():
        raise ValueError(
            "OpsCenter 来源未获批准；请将精确来源加入 OPS_CENTER_ALLOWED_ORIGINS"
        )
    return value


def _service_secret() -> Optional[str]:
    """读取服务间认证密钥，明确拒绝弱值和公开默认密钥。"""
    value = (
        os.environ.get("PO_SECRET_KEY")
        or os.environ.get("OPS_SECRET_KEY")
        or ""
    ).strip()
    if (
        len(value) < MIN_SERVICE_SECRET_LENGTH
        or value == INSECURE_DEFAULT_SECRET
        or value.lower().startswith(("your_", "replace_with_"))
    ):
        return None
    return value


def _create_service_token(secret: str) -> Optional[str]:
    """使用项目声明的 python-jose 签发短时服务令牌。"""
    try:
        from jose import jwt
        import datetime as dt

        token = jwt.encode(
            {
                "user_id": "prompt-engine",
                "username": "prompt-engine",
                "role": "admin",
                "exp": dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=5),
            },
            secret,
            algorithm=JWT_ALGORITHM,
        )
        return token.decode() if isinstance(token, bytes) else token
    except Exception as exc:
        logger.error("无法生成 OpsCenter 服务令牌: %s", exc)
        return None


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
    secret = _service_secret()
    if not secret:
        logger.warning("未配置 OpsCenter 服务密钥，跳过官方密钥请求")
        return []
    token = _create_service_token(secret)
    if not token:
        return []

    import httpx

    try:
        url = f"{_ops_center_url(ops_url)}/api/v1/secrets"
        async with httpx.AsyncClient(timeout=5.0, follow_redirects=False) as client:
            resp = await client.get(
                url,
                params={"provider": provider},
                headers={"Authorization": f"Bearer {token}"},
            )
            if resp.status_code == 200:
                payload = resp.json()
                if not isinstance(payload, dict):
                    return []
                keys = payload.get("keys", [])
                if not isinstance(keys, list):
                    return []
                # Filter by tier_access <= user_tier and is_active
                active = [
                    k for k in keys
                    if isinstance(k, dict)
                    and isinstance(k.get("id"), str)
                    and bool(k.get("id", "").strip())
                    and k.get("provider") == provider
                    and k.get("is_active")
                    and isinstance(k.get("tier_access", 1), (int, float))
                    and k.get("tier_access", 1) <= user_tier
                ]
                active.sort(key=lambda k: k.get("priority", 99))
                return active
    except Exception as e:
        logger.warning("OpsCenter 不可达，使用配置回退密钥: %s", e)
    return []


async def reveal_key(key_id: str, ops_url: Optional[str] = None) -> Optional[str]:
    """Reveal the plaintext of an official key (requires admin auth — for service use).

    Falls back to returning None if OpsCenter is unreachable.
    """
    secret = _service_secret()
    if not secret:
        logger.warning("未配置 OpsCenter 服务密钥，跳过明文密钥请求")
        return None
    token = _create_service_token(secret)
    if not token:
        return None

    import httpx

    try:
        safe_key_id = quote(key_id, safe="")
        url = f"{_ops_center_url(ops_url)}/api/v1/secrets/{safe_key_id}/reveal"
        async with httpx.AsyncClient(timeout=5.0, follow_redirects=False) as client:
            resp = await client.post(url, headers={"Authorization": f"Bearer {token}"})
            if resp.status_code == 200:
                payload = resp.json()
                if not isinstance(payload, dict):
                    return None
                api_key = payload.get("api_key")
                if isinstance(api_key, str) and api_key.strip():
                    return api_key.strip()
    except Exception as e:
        logger.warning("无法揭示密钥 %s: %s", key_id, e)
    return None
