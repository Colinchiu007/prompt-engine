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

# 导演工作流上限（Higgsfield P0；对齐契约层 video-prompt-engine-contract.js VIDEO_ENGINE_LIMITS）
VIDEO_DIRECTOR_LIMITS = {
    "excluded_characters_max": 10,
    "no_swap_pairs_max": 5,
    "shots_max": 3,
    "beats_per_shot_max": 6,
    "shot_duration_max": 15,
    "beat_time_max": 40,
    "beat_action_max": 500,
    "color_ratio_default": "60:30:10",
}

# 结构化输出键（系统提示 Output Format 与 optimizer.JSON_RETRY_HINT 同源，禁止双份手写漂移）
VIDEO_OUTPUT_KEYS = (
    "prompt", "shot", "camera", "motion_intensity", "scene_transition",
    "continuity_token", "duration_hint", "positive_constraints", "final_frame",
    "excluded_characters", "no_swap_pairs", "color_ratio", "shots",
    "audio_layers",
)


class VideoOptimizeRequest(BaseModel):
    """视频提示词优化请求（domain 恒为 video）。"""
    prompt: str = Field(..., min_length=1, max_length=2000, description="原始视频提示词")
    platform: VideoPlatformType | str = Field(default=VideoPlatformType.GENERIC_VIDEO, description="目标视频平台")
    style: Optional[str] = Field(default=None, max_length=50, description="艺术风格（可空，自动检测）")
    creative_level: int = Field(default=5, ge=1, le=10, description="创意程度 1-10")
    max_length: int = Field(default=1800, ge=200, le=20000, description="优化结果最大字符数（批量层默认 1800 字符；精修层 creative_level≥7 上限 20000，对齐契约层 videoMaxLengthMax——500-5000 词导演分镜单 ≈22871 字符）")
    num_candidates: int = Field(default=1, ge=1, le=5, description="候选版本数量")
    negative_prompt: Optional[str] = Field(default=None, max_length=500, description="负面提示词")
    prev_final_frame: Optional[str] = Field(default=None, max_length=1000, description="上一镜终态描述（跨镜承接；trim 后空由契约层丢弃，超长 422 双保险）")
    context: Optional[dict] = Field(default=None, description="上下文（白名单键）")
    output_language: str = Field(default="en", pattern="^(zh|en)$", description="输出语言：en/zh；zh 保留中文主体 + 镜头术语双语，结构化枚举仍英文")


class VideoBatchOptimizeRequest(BaseModel):
    """批量视频提示词优化请求（单批 ≤20 条，有界并发 8）。"""
    requests: list[VideoOptimizeRequest] = Field(..., min_length=1, max_length=20)


class VideoBeat(BaseModel):
    """时间块（Higgsfield 导演工作流：time/action/camera 三元组，≤6/镜头）。"""
    time: str = Field(default="", max_length=50, description="时间锚点（如 0:00-0:04）")
    action: str = Field(default="", max_length=500, description="该时间块内主体动作/事件")
    camera: str = Field(default="", max_length=50, description="该时间块镜头语言")


class VideoShot(BaseModel):
    """镜头单元（≤3 个，每镜头 ≤6 个时间块）。"""
    shot: str = Field(default="", max_length=50, description="镜头编号（如 shot_01）")
    camera: str = Field(default="", max_length=50, description="镜头语言")
    duration: float = Field(default=5.0, ge=1.0, le=15.0, description="镜头时长（秒，1-15）")
    beats: list[VideoBeat] = Field(default_factory=list, max_length=6, description="时间块列表（≤6）")


class VideoPromptMeta(BaseModel):
    """结构化视频字段（shot/camera/motion_intensity/... + Higgsfield 导演维度）。"""
    shot: str = Field(default="", max_length=50)
    camera: str = Field(default="", max_length=50)
    motion_intensity: int = Field(default=5, ge=1, le=10)
    scene_transition: str = Field(default="", max_length=50)
    continuity_token: str = Field(default="", max_length=100)
    duration_hint: Optional[float] = Field(default=None)
    # --- Higgsfield 导演维度（上限对齐 VIDEO_DIRECTOR_LIMITS；新字段全默认值，旧缓存可重建）---
    aspect: str = Field(default="16:9", max_length=10, description="画面比例（默认 16:9）")
    audio: str = Field(default="SFX", max_length=50, description="音频提示（默认 SFX，对齐契约 appendVideoTrailer）")
    audio_layers: Optional[dict] = Field(default=None, description="音频分层（可选：environment/sfx/dialogue 字符串层各 ≤200 字符 + music_off 布尔；默认 None 保持旧尾行）")
    excluded_characters: list[str] = Field(default_factory=list, max_length=10, description="禁止出现角色/元素（≤10）")
    no_swap_pairs: list[dict] = Field(default_factory=list, max_length=5, description="禁止替换对 [{\"from\":...,\"to\":...}]（≤5）")
    color_ratio: str = Field(default="60:30:10", max_length=20, description="色彩配比（默认 60:30:10）")
    shots: list[VideoShot] = Field(default_factory=list, max_length=3, description="镜头单元（≤3，每镜头 ≤6 时间块）")
    positive_constraints: list[str] = Field(default_factory=list, max_length=10, description="正向硬约束（必须如此），STRICT 块来源")
    final_frame: str = Field(default="", max_length=1000, description="最终画面描述（终态：位置/姿势/灯光/机位/禁文字；与 prev_final_frame 同界 1000，防复杂多角色终态丢实体）")
    blocks: Optional[dict] = Field(default=None, description="导演分镜块骨架（12 块白名单键，值 ≤4000；refined 渲染形态与覆盖度检查同源）")


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
    language: str = Field(default="en", description="实际输出语言（zh/en）")
    cache_hit: bool = Field(default=False, description="是否命中缓存（跳过 LLM）")
    retried: int = Field(default=0, description="结构化输出 JSON 重试次数")
    classification: Optional[dict] = Field(default=None, description="输入题材/镜头意图检测结果")


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
        elif isinstance(value, list):
            for j, item in enumerate(value):
                if isinstance(item, dict):
                    assert_no_sensitive_context(item, f"{field}.{key}[{j}]")
                elif isinstance(item, list):
                    assert_no_sensitive_context({"__nested_list__": item}, f"{field}.{key}[{j}]")


class VideoFeedbackRequest(BaseModel):
    """视频提示词反馈（好/坏反馈 → 种子库沉淀或质量分降级）。"""

    prompt_text: str = Field(..., min_length=1, max_length=2000, description="源提示词（用户输入原文）")
    result_prompt: str = Field(..., min_length=1, max_length=20000, description="引擎输出的优化提示词（refined 层上限 20000，对齐 max_length 边界上浮）")
    good: bool = Field(default=True, description="true=好评（结果沉淀入种子库，质量分 9）；false=坏评（源提示词质量分降级）")
    source: str = Field(default="user-feedback", max_length=100, description="反馈来源标注")
    failure_patterns: list[str] = Field(default_factory=list, max_length=10, description="坏评失败模式标签（P1-3：对齐 failure_patterns.json 规则库 pattern 键，用于失败模式闭环统计）")


class VideoClassifyRequest(BaseModel):
    """输入分类请求（题材/镜头意图检测，用于自动选策略与关键词维度）。"""

    prompt: str = Field(..., min_length=1, max_length=2000, description="原始输入提示词/文案")
