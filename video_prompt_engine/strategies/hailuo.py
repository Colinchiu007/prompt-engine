"""Hailuo 平台策略 — 节奏/剪辑/氛围（首版近似）。"""
from video_prompt_engine.models import VideoPlatformType
from video_prompt_engine.strategies.generic_video import GenericVideoStrategy, register


@register("hailuo")
class HailuoStrategy(GenericVideoStrategy):
    platform = VideoPlatformType.HAILUO

    @classmethod
    def build_system_prompt(cls, style=None, creative_level=5, max_length=1800, negative_prompt=None, keywords_hint="", output_language="en", character_count=None):
        base = super().build_system_prompt(style, creative_level, max_length, negative_prompt, keywords_hint, output_language, character_count)
        note = """
## Hailuo Platform Notes
- Hailuo favors rhythm, pacing, and mood; describe tempo (slow-burn / fast-cut) explicitly.
- Scene transitions matter; specify cut/fade/dissolve intent and rhythm cues."""
        return base.replace("## Output Format (MANDATORY)", note + "\n\n## Output Format (MANDATORY)")
