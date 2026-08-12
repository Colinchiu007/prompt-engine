"""视频领域数据模型（自包含，不依赖 prompt_engine.models）。

与图片引擎模型完全解耦：视频平台枚举、视频优化请求/结果、结构化 video 字段、
context 白名单、批量契约（≤20）。
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class VideoPlatformType(str, Enum):
    """支持的视频生成平台（首期：通用兜底 + Seedance 专项；其余平台策略随后续注册）。"""
    VEO = "veo"
    KLING = "kling"
    SEEDANCE = "seedance"
    HAILUO = "hailuo"
    DOUBAO = "doubao"
    RUNWAY = "runway"
    MINIMAX = "minimax"
    HUNYUAN = "hunyuan"
    COGVIDEO = "cogvideo"
    GENERIC_VIDEO = "generic_video"


# 平台别名（发送前归一，防止 422）
VIDEO_PLATFORM_ALIASES = {
    "veo3": "veo",
    "veo-3": "veo",
    "veo-3.1": "veo",
    "kling-v2": "kling",
    "kling-v3": "kling",
    "seedance-2.0": "seedance",
    "seedance-2.5": "seedance",
    "hailuo-2": "hailuo",
    "doubao-1.5": "doubao",
    "runway-gen4": "runway",
    "cogvideo-5b": "cogvideo",
}

# context 白名单键（对齐视频内容保真契约；未知键忽略 + warning）
CONTEXT_KEYS = frozenset({
    "synopsis", "character", "setting", "character_list", "full_text",
    "narrative_intent", "scene_type",
})

SENSITIVE_CONTEXT_KEYS = frozenset({
    "api_key", "apikey", "token", "secret", "password", "authorization",
})


class VideoOptimizeRequest(BaseModel):
    """视频提示词优化请求（domain 恒为 video）。"""
    prompt: str = Field(..., min_length=1, max_length=2000, description="原始视频提示词")
    platform: VideoPlatformType | str = Field(default=VideoPlatformType.GENERIC_VIDEO, description="目标视频平台")
    style: Optional[str] = Field(default=None, max_length=50, description="艺术风格（可空，自动检测）")
    creative_level: int = Field(default=5, ge=1, le=10, description="创意程度 1-10")
    max_length: int = Field(default=1800, ge=200, le=4000, description="优化结果最大字符数（视频提示词专业长度 150-300 词，默认 1800 字符）")
    num_candidates: int = Field(default=1, ge=1, le=5, description="候选版本数量")
    negative_prompt: Optional[str] = Field(default=None, max_length=500, description="负面提示词")
    context: Optional[dict] = Field(default=None, description="上下文（白名单键）")


class VideoBatchOptimizeRequest(BaseModel):
    """批量视频提示词优化请求（单批 ≤20 条，有界并发 8）。"""
    requests: list[VideoOptimizeRequest] = Field(..., min_length=1, max_length=20)


class VideoPromptMeta(BaseModel):
    """结构化视频字段（shot/camera/motion_intensity/...）。"""
    shot: str = Field(default="", max_length=50)
    camera: str = Field(default="", max_length=50)
    motion_intensity: int = Field(default=5, ge=1, le=10)
    scene_transition: str = Field(default="", max_length=50)
    continuity_token: str = Field(default="", max_length=100)
    duration_hint: Optional[float] = Field(default=None)


class VideoOptimizeResult(BaseModel):
    """视频优化结果（fail closed：error 优先 → detail → optimized_prompt 非空）。"""
    optimized_prompt: str = Field(default="", description="渲染单串（provider 直用）")
    platform: str = Field(default="generic_video")
    style: Optional[str] = Field(default=None)
    model_used: str = Field(default="")
    tokens_used: int = Field(default=0)
    duration_ms: float = Field(default=0.0)
    candidates: list[str] = Field(default_factory=list)
    video: Optional[VideoPromptMeta] = Field(default=None, description="结构化视频字段")
    error: Optional[str] = Field(default=None)
    detail: Optional[str] = Field(default=None)


def normalize_video_platform(value: Any) -> str:
    """视频平台归一：别名 → 枚举；未知回退 generic_video。"""
    if isinstance(value, VideoPlatformType):
        return value.value
    raw = str(value or "").strip().lower()
    if raw in VIDEO_PLATFORM_ALIASES:
        return VIDEO_PLATFORM_ALIASES[raw]
    if raw in {p.value for p in VideoPlatformType}:
        return raw
    return VideoPlatformType.GENERIC_VIDEO.value


def assert_no_sensitive_context(context: dict, field: str = "context") -> None:
    """context 敏感键拦截（递归，命中抛错）。"""
    def norm_key(k: str) -> str:
        return str(k or "").strip().lower().replace("-", "_")
    for key, value in context.items():
        if norm_key(key) in SENSITIVE_CONTEXT_KEYS:
            raise ValueError(f"{field}.{key} 包含敏感凭据键，已拒绝外发")
        if isinstance(value, dict):
            assert_no_sensitive_context(value, f"{field}.{key}")
