"""Veo 平台策略 — 长镜头/真实感/电影质感（首版基于公开资料近似）。"""
from video_prompt_engine.models import VideoPlatformType
from video_prompt_engine.strategies.generic_video import GenericVideoStrategy, register


@register("veo")
class VeoStrategy(GenericVideoStrategy):
    platform = VideoPlatformType.VEO

    @classmethod
    def build_system_prompt(cls, style=None, creative_level=5, max_length=1800, negative_prompt=None, keywords_hint="", output_language="en", tier="batch"):
        base = super().build_system_prompt(style, creative_level, max_length, negative_prompt, keywords_hint, output_language, tier=tier)
        platform_note = """
## Veo Platform Notes
- Veo excels at long continuous takes, realistic physics, and natural camera language.
- Prefer smooth, continuous camera motion; avoid rapid cuts unless specified.
- Keep subject motion physically plausible with realistic lighting and texture detail.
- Output duration can be 5-15s; describe a single continuous shot unless multi-shot is intended.
- Veo is optimized for English prompts; prefer English descriptive prose for best quality (aligns with language routing: veo -> en)."""
        return base.replace("## Output Format (MANDATORY)", platform_note + "\n\n## Output Format (MANDATORY)")
