"""豆包平台策略 — 中文优先（首版近似）。"""
from video_prompt_engine.models import VideoPlatformType
from video_prompt_engine.strategies.generic_video import GenericVideoStrategy, register


@register("doubao")
class DoubaoStrategy(GenericVideoStrategy):
    platform = VideoPlatformType.DOUBAO

    @classmethod
    def build_system_prompt(cls, style=None, creative_level=5, max_length=1800, negative_prompt=None, keywords_hint="", output_language="en", tier="batch", character_count=None):
        base = super().build_system_prompt(style, creative_level, max_length, negative_prompt, keywords_hint, output_language, tier=tier, character_count=character_count)
        note = """
## Doubao Platform Notes
- Doubao has strong Chinese-language understanding; Chinese descriptions are well supported.
- Prefer Chinese output (output_language=zh): Chinese subject-action-environment structure yields the highest fidelity (aligns with language routing: doubao -> zh).
- Prefer vivid scene description with clear subject-action-environment structure."""
        return base.replace("## Output Format (MANDATORY)", note + "\n\n## Output Format (MANDATORY)")
