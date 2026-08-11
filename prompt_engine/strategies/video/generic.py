"""视频通用平台策略 — 平台无关的视频提示词优化（Phase 1 兜底）

设计原则：
1. 输出英文（主流视频模型英文效果最佳）
2. 六要素：主体 → 动作 → 环境 → 光色 → 风格 → 镜头语言
3. 视频特有维度：景别(shot)、机位/镜头运动(camera)、运动强度(motion_intensity)、转场(scene_transition)、时长(duration_hint)
4. 结构化 JSON 输出 + 渲染单串双形态：provider 直用渲染单串，上层编排读结构化字段
"""
from __future__ import annotations

import json
import re
from typing import Any

from prompt_engine.models import StyleType, VideoPlatformType
from prompt_engine.strategies.base import BaseStrategy, register

VIDEO_SHOT_TYPES = ("extreme_close_up", "close_up", "medium", "medium_wide", "wide", "establishing")
VIDEO_CAMERA_MOTIONS = ("static", "pan", "tilt", "dolly", "track", "crane", "handheld", "drone", "zoom_in", "zoom_out", "orbit")
VIDEO_TRANSITIONS = ("cut", "fade", "dissolve", "wipe", "match_cut")


def _clamp_int(value: Any, lo: int = 1, hi: int = 10, default: int = 5) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


@register("generic_video")
class GenericVideoStrategy(BaseStrategy):
    """视频通用提示词策略 — 生成平台无关的高质量视频提示词"""

    domain = "video"
    platform = VideoPlatformType.GENERIC_VIDEO

    @classmethod
    def build_system_prompt(
        cls,
        style: StyleType | None = None,
        creative_level: int = 5,
        max_length: int = 500,
        negative_prompt: str | None = None,
    ) -> str:
        style_text = f"，风格：{style.value}" if style else ""
        negative_text = cls.build_negative_section(negative_prompt)

        if creative_level <= 3:
            detail_instruction = "简洁精炼，保留核心视觉要点"
        elif creative_level <= 6:
            detail_instruction = "适中细节描写，兼顾画面与运动"
        else:
            detail_instruction = "丰富细腻：细节、氛围、情绪、镜头调度"

        return f"""You are an expert prompt engineer for AI VIDEO generation. Transform user descriptions into high-quality, platform-agnostic video prompts.

## Core Principle: Platform-Agnostic
- Works across major video models (Sora, Kling, Veo, Runway, Wan, Seedance, MiniMax, Hunyuan, CogVideo, LTX, Higgsfield, Grok).
- No platform-specific syntax. Use universal descriptive language.

## Output Structure (MANDATORY — follow this order)
1. **Subject** — main subject: appearance, clothing, pose, expression, details
2. **Action/Motion** — what is happening, subject motion, motion intensity
3. **Environment** — setting, background, props, atmosphere
4. **Color Palette** — dominant colors and relationships
5. **Lighting** — source, quality, direction, effects (e.g. "golden hour rim light", "soft diffused daylight")
6. **Style/Shot/Camera** — artistic style, shot scale, camera angle and camera motion (e.g. "cinematic medium-wide shot, slow dolly-in")

## Video-Specific Guidance
- **Shot scale**: extreme_close_up / close_up / medium / medium_wide / wide / establishing
- **Camera motion**: static / pan / tilt / dolly / track / crane / handheld / drone / zoom_in / zoom_out / orbit
- **Motion intensity**: {creative_level}/10 (low=subtle ambient motion, high=dynamic action)
- **Transition**: cut / fade / dissolve / wipe (default cut for single clip)
- **Physics & consistency**: motion must be physically plausible; keep subject identity/colors consistent across the clip; avoid text, logos, watermarks, morphing, or extra limbs.

## Detail Level Control
- creative_level={creative_level}/10: {detail_instruction}

## Output Format (MANDATORY)
Output ONLY a JSON object with EXACTLY these keys:
{{
  "prompt": "the rendered single-string video prompt (English, flowing prose, within {max_length} chars)",
  "shot": "one of {VIDEO_SHOT_TYPES}",
  "camera": "one of {VIDEO_CAMERA_MOTIONS}",
  "motion_intensity": {creative_level},
  "scene_transition": "one of {VIDEO_TRANSITIONS}",
  "continuity_token": "a short stable token describing character/scene/style for cross-scene consistency (or empty string)",
  "duration_hint": null
}}
No explanations, no markdown fences, no text outside the JSON object.
{style_text}
{negative_text}"""

    @classmethod
    def parse_video_json(cls, raw_output: str) -> dict[str, Any] | None:
        """解析 LLM 结构化输出；非法 JSON 返回 None（由调用方规则化回退）。"""
        text = str(raw_output or "").strip()
        if not text:
            return None
        # 去掉 markdown 围栏
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE).strip()
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return None
        if not isinstance(data, dict):
            return None
        return data

    @classmethod
    def render(cls, data: dict[str, Any], creative_level: int = 5) -> str:
        """从结构化字段渲染单串提示词。"""
        prompt = str(data.get("prompt") or "").strip()
        if prompt:
            return prompt
        # 无 prompt 字段时按六要素规则化拼接
        parts = []
        for key in ("subject", "action", "environment", "colors", "lighting", "style"):
            val = str(data.get(key) or "").strip()
            if val:
                parts.append(val)
        if parts:
            return " ".join(parts)
        return ""

    @classmethod
    def extract_video_meta(cls, raw_output: str) -> dict[str, Any] | None:
        data = cls.parse_video_json(raw_output)
        if data is None:
            return None
        duration_hint = data.get("duration_hint")
        try:
            duration = float(duration_hint) if duration_hint is not None and str(duration_hint).strip() != "" else None
        except (TypeError, ValueError):
            duration = None
        return {
            "shot": str(data.get("shot") or "").strip(),
            "camera": str(data.get("camera") or "").strip(),
            "motion_intensity": _clamp_int(data.get("motion_intensity"), default=creative_level_safe(data)),
            "scene_transition": str(data.get("scene_transition") or "").strip(),
            "continuity_token": str(data.get("continuity_token") or "").strip(),
            "duration_hint": duration,
        }

    @classmethod
    def post_process_video(cls, raw_output: str, creative_level: int = 5) -> tuple[str, dict[str, Any]]:
        """视频策略专用：返回 (渲染单串, 结构化字段 dict)。"""
        data = cls.parse_video_json(raw_output)
        if data is None:
            rendered = str(raw_output or "").strip().strip('"').strip()
            return rendered, {}
        rendered = cls.render(data, creative_level)
        meta = cls.extract_video_meta(raw_output)
        return rendered, (meta or {})

    @classmethod
    def post_process(cls, raw_output: str, creative_level: int = 5,
                     preferred_categories: list[str] | None = None) -> str:
        rendered, _meta = cls.post_process_video(raw_output, creative_level)
        return rendered


def creative_level_safe(data: dict[str, Any]) -> int:
    """从 data 中读取 motion_intensity 缺省时的兜底值。"""
    raw = data.get("motion_intensity")
    try:
        return max(1, min(10, int(raw))) if raw is not None else 5
    except (TypeError, ValueError):
        return 5
