"""通用视频平台策略 — 平台无关的视频提示词优化（首期兜底）。

机制复刻图片引擎 generic 策略（六要素 + 结构化输出），独立实现并追加：
- Fact-Fidelity：不得改变主体身份/时代/事件事实（视频内容保真）
- 视频维度关键词提示（keywords_hint）
"""
from __future__ import annotations

from typing import Any, Optional

from video_prompt_engine.models import VideoPlatformType, VIDEO_OUTPUT_KEYS
from video_prompt_engine.strategies.base import BaseVideoStrategy, register
from video_prompt_engine.knowledge.loader import load_director_styles, resolve_director_style

VIDEO_SHOT_TYPES = ("extreme_close_up", "close_up", "medium", "medium_wide", "wide", "establishing")
VIDEO_CAMERA_MOTIONS = ("static", "pan", "tilt", "dolly", "track", "crane", "handheld", "drone", "zoom_in", "zoom_out", "orbit")
VIDEO_TRANSITIONS = ("cut", "fade", "dissolve", "wipe", "match_cut")

# P1-6 导演风格词典（DEEP 报告）：knowledge/director_styles.json 17 位导演/摄影指导
_DIRECTOR_STYLES = load_director_styles(
    __import__("pathlib").Path(__file__).resolve().parent.parent / "knowledge" / "director_styles.json"
)


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
        # P1-6 导演风格引用：style 命中导演/摄影指导名时注入一句话风格（如 "Lubezki 风格"）
        director = resolve_director_style(style or "", _DIRECTOR_STYLES)
        if director:
            style_text += f"（导演风格引用：{director['style_desc']}）"
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
        # 评审 W2：refined 层 keys 追加 "blocks"（与 blocks_sample 同源，batch 零回归）
        keys = list(VIDEO_OUTPUT_KEYS)
        if tier == "refined":
            keys.append("blocks")
        keys_line = ", ".join(f'"{k}"' for k in keys)
        # Round3 C：refined 层 JSON 样例附加 blocks 键（batch 不输出，保持字节级零回归）
        blocks_sample = (
            ',\n  "blocks": {"SCENE NOTE": "scene pickup & current state (required when prev_final_frame provided)", "SPATIAL LAYOUT": "blocking and frame composition", "LIGHTING": "sources, quality, direction", "COLOR": "dominant palette and ratios", "CAMERA": "shot scale, angle, lens, camera motion", "ENVIRONMENT": "setting, props, weather", "CONTINUITY": "cross-scene consistency tokens", "CHARACTERS": "who appears, wardrobe, identity locks", "SKIN": "pore-level realism notes", "ACTING": "performance direction", "STILLNESS LOCK": "elements that must NOT move", "FINAL FRAME": "explicit end state"}'
            if tier == "refined" else ""
        )
        # 长度口径与 evaluator tier 层级对齐（DEEP P0-1）：refined 500-5000 词（zh 500 字符-预算上限）；
        # max_length 是字符预算上限不是目标长度——小预算（如 1800）下 LLM 写不满 500 词属正常，
        # evaluator 下界随预算自适应（评审 C1/W4），不再要求「fill the budget」与词数下限同时成立
        length_instruction = (
            f"Write a RICH, DETAILED video prompt of 500-5000 English words (Chinese: 500 chars up to the {max_length} char budget), staying within the {max_length} char budget — scale length to the budget, covering ALL shots. NOT a short one-liner."
            if tier == "refined"
            else "Write a RICH, DETAILED video prompt of 150-300 words (about 900-2000 chars) — NOT a short one-liner."
        )

        director_look = director["look"] if director else ""
        return f"""You are an expert prompt engineer for AI VIDEO generation. Transform user descriptions into high-quality, platform-agnostic video prompts.

## Core Principle: Platform-Agnostic
- Works across major video models (Veo, Kling, Seedance, Hailuo, Doubao, Runway, MiniMax, Hunyuan, CogVideo).
- Use universal descriptive language.

## Director Style Reference
- When a director/DP style is referenced in the style field, apply its visual language: {director_look}

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
  "shots": [{{"shot": "shot_01", "camera": "camera motion", "duration": 5, "beats": [{{"time": "0:00-0:04", "action": "...", "camera": "..."}}]}}],
  "audio_layers": null{blocks_sample}
}}
IMPORTANT (timeline markers): when `shots` has 2 or more units, the rendered `prompt` body MUST embed a cut marker at each shot boundary: `[SHOT N]` (N = 1, 2, ...) or `[HARD CUT]` — e.g. "[SHOT 1] hero enters the hall. [HARD CUT] hero draws his sword." Single-shot prompts do NOT need markers.
No explanations, no markdown fences, no text outside the JSON object.
{cls.build_higgsfield_section(tier)}
{style_text}
{negative_text}"""
