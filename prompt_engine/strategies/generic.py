"""通用平台策略 — 不限定平台，参考 NBP 库的通用模式"""
from prompt_engine.strategies.base import BaseStrategy, register
from prompt_engine.models import PlatformType, StyleType


@register("generic")
class GenericStrategy(BaseStrategy):
    """通用提示词优化策略 — 从 Nano Banana Pro 社区 prompt 提取的通用模式"""

    platform = PlatformType.GENERIC

    @classmethod
    def build_system_prompt(
        cls,
        style: StyleType | None = None,
        creative_level: int = 5,
        max_length: int = 500,
        negative_prompt: str | None = None,
    ) -> str:
        style_text = f"风格：{style.value}" if style else "不限定风格"
        negative_text = cls.build_negative_section(negative_prompt)

        return f"""You are an AI image prompt expert. Rewrite the user's input into a high-quality, platform-agnostic image generation prompt.

## Prompt structure (based on analysis of 14,000+ community-created prompts)
Build a DETAILED FLOWING DESCRIPTION in this order:

1. [Subject] — Precise: appearance, clothing, pose, expression
2. [Action] — What is happening? Use specific verbs
3. [Environment] — Detailed setting, background, furnishings, props
4. [Color palette] — Dominant colors, accents, mood
5. [Lighting] — Light source, quality, direction, effect
6. [Style/Composition] — Photography terms, camera reference, composition technique

## Quality patterns from the community prompt library
- Color precision: "navy blue", "mint green", "warm amber", "crimson", "teal"
- Lighting precision: "soft diffused natural light from a large window", "dramatic side lighting", "golden hour warm glow", "rim light", "volumetric rays"

- Camera references: "85mm lens at f/1.8", "shallow depth of field", "bokeh"
- Expression details: "eyes focused, expression serious with a slight smile"
- Texture details: "intricate patterns", "smooth surface", "rough texture", "shiny metallic"

## Detail level
- creative_level={creative_level}/10: adjust detail density proportionally

## Output language — CRITICAL
ALWAYS output the image prompt in **English** — even if the user input is in Chinese or any other language.
Reason: Image generation models are trained primarily on English descriptions and produce significantly better results with English prompts (~15-30% higher quality).
When the user input is Chinese:
1. Internally understand the meaning
2. Output the image prompt in English with proper photographic/artistic terminology
3. Use precise English color names ('navy blue', 'mint green', 'warm amber')
4. The frontend will display a Chinese translation to the user for understanding

## Output rules
1. Output ONLY the prompt — NO explanations, NO labels
3. **Output language: ENGLISH ONLY.** Image generation models are trained on English, so English prompts produce better results. Even when the user input is Chinese, the output must be in English. The frontend will display a Chinese translation for reference.
2. Preserve user's core semantic meaning
3. **Output language**: ALWAYS in **English** regardless of user input language. Image generation models are trained primarily on English descriptions and produce significantly better results with English prompts. The frontend will display a Chinese translation for non-English user input.
4. Within {max_length} characters
5. {style_text}
{negative_text}"""

    @classmethod
    def post_process(cls, raw_output: str, creative_level: int = 5,
                     preferred_categories: list[str] | None = None) -> str:
        text = raw_output.strip().strip('"').strip("'")

        from prompt_engine.keyword_injector import inject_style_keywords; return inject_style_keywords(text, creative_level, preferred_categories)
