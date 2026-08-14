"""通用视频平台策略 — 平台无关的视频提示词优化（首期兜底）。

机制复刻图片引擎 generic 策略（六要素 + 结构化输出），独立实现并追加：
- Fact-Fidelity：不得改变主体身份/时代/事件事实（视频内容保真）
- 视频维度关键词提示（keywords_hint）
"""
from __future__ import annotations

from typing import Any, Optional

from video_prompt_engine.models import VideoPlatformType, VIDEO_OUTPUT_KEYS
from video_prompt_engine.strategies.base import BaseVideoStrategy, register

VIDEO_SHOT_TYPES = ("extreme_close_up", "close_up", "medium", "medium_wide", "wide", "establishing")
VIDEO_CAMERA_MOTIONS = ("static", "pan", "tilt", "dolly", "track", "crane", "handheld", "drone", "zoom_in", "zoom_out", "orbit")
VIDEO_TRANSITIONS = ("cut", "fade", "dissolve", "wipe", "match_cut")


@register("generic_video")
class GenericVideoStrategy(BaseVideoStrategy):
    """视频通用策略 — 六要素 + Fact-Fidelity + 镜头语言。"""

    platform = VideoPlatformType.GENERIC_VIDEO

    @classmethod
    def build_system_prompt(
        cls,
        style: Optional[str] = None,
        creative_level: int = 5,
        max_length: int = 500,
        negative_prompt: Optional[str] = None,
        keywords_hint: str = "",
        output_language: str = "en",
        tier: str = "batch",
        character_count: Optional[int] = None,
    ) -> str:
        style_text = f"，风格：{style}" if style else ""
        negative_text = cls.build_negative_section(negative_prompt)
        if creative_level <= 3:
            detail_instruction = "简洁精炼，保留核心视觉要点"
        elif creative_level <= 6:
            detail_instruction = "适中细节描写，兼顾画面与运动"
        else:
            detail_instruction = "丰富细腻：细节、氛围、情绪、镜头调度"

        keywords = f"\n## 视频关键词参考\n{keywords_hint}" if keywords_hint else ""
        lang_note = "Chinese 中文主体 + 英文镜头术语双语" if str(output_language or "en").lower().startswith("zh") else "English"
        lang_section = cls.build_language_section(output_language, tier=tier)
        lens_discipline = cls.build_lens_discipline_section(character_count)
        keys_line = ", ".join(f'"{k}"' for k in VIDEO_OUTPUT_KEYS)
        # 长度口径与 evaluator tier 层级对齐：refined 500+ 词/500-5000 中文字符（随预算缩放）；batch 150-300 词（W8）
        length_instruction = (
            f"Write a RICH, DETAILED video prompt of 500+ English words (500-5000 Chinese chars) — fill the {max_length} char budget as far as possible (scale length to the budget), covering ALL shots. NOT a short one-liner."
            if tier == "refined"
            else "Write a RICH, DETAILED video prompt of 150-300 words (about 900-2000 chars) — NOT a short one-liner."
        )

        return f"""You are an expert prompt engineer for AI VIDEO generation. Transform user descriptions into high-quality, platform-agnostic video prompts.

## Core Principle: Platform-Agnostic
- Works across major video models (Veo, Kling, Seedance, Hailuo, Doubao, Runway, MiniMax, Hunyuan, CogVideo).
- Use universal descriptive language.

## Fact-Fidelity (MANDATORY)
- Do NOT change the subject's identity, era/setting, or event facts from the input.
- If context provides synopsis/full_text, visual elements MUST stay consistent with those facts.
- Do NOT add plot details that contradict the input.

## Output Structure (MANDATORY — follow this order)
1. **Subject** — main subject: appearance, clothing, pose, expression, details
2. **Action/Motion** — what is happening, subject motion, motion intensity
3. **Environment** — setting, background, props, atmosphere
4. **Color Palette** — dominant colors and relationships
5. **Lighting** — source, quality, direction, effects (e.g. "golden hour rim light")
6. **Style/Shot/Camera** — artistic style, shot scale, camera angle and camera motion

## Video-Specific Guidance
- **Shot scale**: extreme_close_up / close_up / medium / medium_wide / wide / establishing
- **Camera motion**: static / pan / tilt / dolly / track / crane / handheld / drone / zoom_in / zoom_out / orbit
- **Motion intensity**: {creative_level}/10 (low=subtle ambient motion, high=dynamic action)
- **Transition**: cut / fade / dissolve / wipe (default cut for single clip)
- **Physics & consistency**: motion must be physically plausible; keep subject identity/colors consistent; avoid text, logos, watermarks, morphing, or extra limbs.

## Detail Level Control
- creative_level={creative_level}/10: {detail_instruction}

## Length & Detail (MANDATORY)
- {length_instruction}
- Describe subject appearance/wardrobe/pose/expression, concrete action & motion, environment & props, color palette, lighting direction/quality, artistic style, shot scale, camera angle & motion, and cross-clip continuity.
- Professional video prompts are long and specific: every visual element the model needs to render should be in the text. Do not truncate early.
{keywords}{lang_section}{lens_discipline}
## Output Format (MANDATORY)
Output ONLY a strict JSON object with EXACTLY these keys: {keys_line}.
{{
  "prompt": "the rendered single-string video prompt ({lang_note}, flowing prose, within {max_length} chars)",
  "shot": "one of {VIDEO_SHOT_TYPES}",
  "camera": "one of {VIDEO_CAMERA_MOTIONS}",
  "motion_intensity": {creative_level},
  "scene_transition": "one of {VIDEO_TRANSITIONS}",
  "continuity_token": "a short stable token describing character/scene/style for cross-scene consistency (or empty string)",
  "duration_hint": null,
  "positive_constraints": ["array of STRICT must-happen constraints, e.g. \"camera stays at ground level\", \"all fallen bodies are distinct\" (or empty array)"],
  "final_frame": "explicit ending state: subject position, pose, lighting state, whether the camera rests, and a no-text statement (non-empty string)",
  "excluded_characters": ["character/element that MUST NOT appear (≤10, or empty array)"],
  "no_swap_pairs": [{{"from": "must-not-appear", "to": "replacement"}}],
  "color_ratio": "60:30:10",
  "shots": [{{"shot": "shot_01", "camera": "camera motion", "duration": 5, "beats": [{{"time": "0:00-0:04", "action": "...", "camera": "..."}}]}}]
}}
No explanations, no markdown fences, no text outside the JSON object.
{cls.build_higgsfield_section(tier)}
{style_text}
{negative_text}"""
