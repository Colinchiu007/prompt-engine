"""Kling 平台策略 — 运动物理/细节/动态表现（首版近似）。"""
from video_prompt_engine.models import VideoPlatformType
from video_prompt_engine.strategies.generic_video import GenericVideoStrategy, register


@register("kling")
class KlingStrategy(GenericVideoStrategy):
    platform = VideoPlatformType.KLING

    @classmethod
    def build_system_prompt(cls, style=None, creative_level=5, max_length=1800, negative_prompt=None, keywords_hint="", output_language="en"):
        base = super().build_system_prompt(style, creative_level, max_length, negative_prompt, keywords_hint, output_language)
        note = """
## Kling Platform Notes
- Kling emphasizes motion physics, dynamic action, and fine detail (fabric, hair, water, particles).
- Describe concrete dynamic motion and interaction between subject and environment.
- Avoid morphing or limb artifacts; keep identity consistent."""
        return base.replace("## Output Format (MANDATORY)", note + "\n\n## Output Format (MANDATORY)")
