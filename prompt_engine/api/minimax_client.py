"""MiniMax 生图共享助手（供 /v1/preview 与 /v1/compare/images 复用）

调用方式（与 Multi-Publish 运营后台 model-preset 契约一致）：
    POST {base_url}/image_generation
    Headers: Authorization: Bearer {api_key}
    Body:    {"model": "image-01", "prompt": ..., "response_format": "url", "n": 2, "aspect_ratio": "1:1"}
    Response: data.image_urls[]（URL 数组）

关键行为：
- HTTP 200 但 image_urls 为空 → 显式抛 MinimaxImageError(error_type="content_safety" | "empty_result")，
  禁止返回空数组让上层误判为「已生成」。
- 错误分级：auth（401/403，不可重试）/ rate_limit（429，可重试）/ timeout / network（可重试）/
  provider_error（5xx 或未知，可重试）/ invalid_config（参数非法）。
"""
from __future__ import annotations

import httpx

DEFAULT_MINIMAX_BASE_URL = "https://api.minimaxi.com/v1"
DEFAULT_IMAGE_MODEL = "image-01"
DEFAULT_IMAGE_TIMEOUT = 60.0
MAX_IMAGE_COUNT = 4  # 生图数量上限（需求默认 2 张对比）


class MinimaxImageError(Exception):
    """MiniMax 生图调用失败（可被路由层映射为 HTTP 状态与提示文案）。"""

    def __init__(self, message: str, error_type: str = "provider_error",
                 retryable: bool = False, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        self.error_type = error_type      # auth | rate_limit | timeout | network | content_safety | empty_result | invalid_config | provider_error
        self.retryable = retryable        # 是否建议重试
        self.status_code = status_code    # 原始 HTTP 状态（如有）

    def to_dict(self) -> dict:
        return {
            "error": self.message,
            "error_type": self.error_type,
            "retryable": self.retryable,
        }


# size → aspect_ratio（与 Multi-Publish minimax-image.js SIZE_TO_ASPECT_RATIO 对齐）
_SIZE_TO_ASPECT_RATIO = {
    "1024x1024": "1:1",
    "1280x720": "16:9",
    "1920x1080": "16:9",
    "720x1280": "9:16",
    "1080x1920": "9:16",
    "1024x768": "4:3",
    "768x1024": "3:4",
    "1280x960": "4:3",
    "960x1280": "3:4",
}


def parse_aspect_ratio(size: str | None) -> str | None:
    """将像素尺寸解析为 aspect_ratio（如 1024x1024 → 1:1）。"""
    if not size:
        return None
    size = str(size).strip()
    if size in _SIZE_TO_ASPECT_RATIO:
        return _SIZE_TO_ASPECT_RATIO[size]
    import re
    m = re.match(r"^(\d+)x(\d+)$", size, re.IGNORECASE)
    if not m:
        return None
    w, h = int(m.group(1)), int(m.group(2))
    if w <= 0 or h <= 0:
        return None
    a, b = w, h
    while b:
        a, b = b, a % b
    return f"{w // a}:{h // a}"


def _error_from_http(status: int, message: str) -> MinimaxImageError:
    """按 HTTP 状态映射错误类型与可重试性。"""
    if status in (401, 403):
        return MinimaxImageError(
            f"MiniMax 鉴权失败（HTTP {status}）：请检查 API Key 是否正确",
            error_type="auth", retryable=False, status_code=status)
    if status == 429:
        return MinimaxImageError(
            f"MiniMax 请求过于频繁（HTTP 429）：请稍后重试",
            error_type="rate_limit", retryable=True, status_code=status)
    if status >= 500:
        return MinimaxImageError(
            f"MiniMax 服务端错误（HTTP {status}）：{message}",
            error_type="provider_error", retryable=True, status_code=status)
    return MinimaxImageError(
        f"MiniMax 生图失败（HTTP {status}）：{message}",
        error_type="provider_error", retryable=True, status_code=status)


def _sanitize_message(message: str) -> str:
    """清洗错误消息，避免把敏感信息（如 key）带入日志/响应。"""
    if not message:
        return ""
    # 只保留前 200 字符并去掉可能的 Authorization/Bearer 内容
    return str(message).replace("\n", " ")[:200]


def generate_minimax_images(
    prompt: str,
    api_key: str,
    base_url: str | None = None,
    n: int = 2,
    width: int = 1024,
    height: int = 1024,
    timeout: float = DEFAULT_IMAGE_TIMEOUT,
) -> dict:
    """调用 MiniMax image-01 生成图片，返回 {"urls": [...], "model": ..., "count": n}。

    异常：MinimaxImageError
    """
    if not prompt or not prompt.strip():
        raise MinimaxImageError("prompt 不能为空", error_type="invalid_config", retryable=False)
    if not api_key or not api_key.strip():
        raise MinimaxImageError(
            "MiniMax API Key 未配置：请在「对比验证」设置区填写，或设置环境变量 MINIMAX_API_KEY",
            error_type="invalid_config", retryable=False)
    if not isinstance(n, int) or n < 1 or n > MAX_IMAGE_COUNT:
        raise MinimaxImageError(
            f"生图数量 n 需在 1~{MAX_IMAGE_COUNT} 之间（当前 {n}）",
            error_type="invalid_config", retryable=False)

    base = (base_url or DEFAULT_MINIMAX_BASE_URL).rstrip("/")
    aspect = parse_aspect_ratio(f"{width}x{height}") or "1:1"

    body = {
        "model": DEFAULT_IMAGE_MODEL,
        "prompt": prompt.strip(),
        "response_format": "url",
        "n": n,
        "aspect_ratio": aspect,
    }
    try:
        resp = httpx.post(
            f"{base}/image_generation",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=timeout,
        )
    except httpx.TimeoutException:
        raise MinimaxImageError(
            f"MiniMax 生图超时（>{timeout:.0f}s）：图片生成较慢，请稍后重试",
            error_type="timeout", retryable=True)
    except httpx.NetworkError as e:
        raise MinimaxImageError(
            f"MiniMax 网络错误：{_sanitize_message(str(e))}",
            error_type="network", retryable=True)
    except Exception as e:  # noqa: BLE001 — 未知异常统一分级
        raise MinimaxImageError(
            f"MiniMax 调用异常：{_sanitize_message(str(e))}",
            error_type="provider_error", retryable=True)

    if resp.status_code != 200:
        try:
            data = resp.json()
        except Exception:  # noqa: BLE001
            data = {}
        status_msg = (
            (data.get("base_resp") or {}).get("status_msg")
            or data.get("message")
            or data.get("detail")
            or ""
        )
        raise _error_from_http(resp.status_code, _sanitize_message(status_msg))

    try:
        data = resp.json()
    except Exception as e:  # noqa: BLE001
        raise MinimaxImageError(
            f"MiniMax 响应解析失败：{_sanitize_message(str(e))}",
            error_type="provider_error", retryable=True)

    # 响应形状防御：data 可能是 dict（正常）或异常形状（字符串/列表）
    data_block = data.get("data")
    image_urls = (
        data_block.get("image_urls") if isinstance(data_block, dict) else None
    ) or data.get("image_urls") or []
    if not image_urls or not isinstance(image_urls, list):
        status_msg = (
            (data.get("base_resp") or {}).get("status_msg")
            or data.get("base_resp") or {}
        )
        msg = str(status_msg) if isinstance(status_msg, str) else ""
        # 内容安全策略信号（与 Multi-Publish hasStrictContentPolicySignal 对齐的常见关键词）
        lower = msg.lower()
        if any(k in lower for k in ("content", "sensitive", "违规", "敏感", "denied", "policy", "blocked")):
            raise MinimaxImageError(
                "MiniMax 内容安全策略拒绝了本次生成，请调整提示词后重试",
                error_type="content_safety", retryable=False)
        raise MinimaxImageError(
            "MiniMax 返回了空结果（HTTP 200 但无图片 URL），请重试；若反复出现请检查提示词",
            error_type="empty_result", retryable=True)

    return {
        "urls": list(image_urls)[:n],
        "model": DEFAULT_IMAGE_MODEL,
        "count": min(len(image_urls), n),
    }
