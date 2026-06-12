"""DALL·E 平台策略 — 自然语言风格，源自 NBP 库模式"""
from prompt_engine.strategies.base import BaseStrategy, register
from prompt_engine.models import PlatformType, StyleType


# 风格描述词汇
_STYLE_DESCRIPTIONS = {
    StyleType.PHOTOGRAPHY:
        "Ultra-realistic photographic style. Professional photography with "
        "precise lighting, natural skin texture, and authentic depth of field.",
    StyleType.ANIME:
        "Japanese anime illustration style. Clean linework, vibrant cel shading, "
        "expressive character design with large expressive eyes and dynamic poses.",
    StyleType.CARTOON:
        "Playful cartoon illustration style. Bold outlines, bright colors, "
        "exaggerated proportions, whimsical and fun atmosphere.",
    StyleType.OIL_PAINTING:
        "Classical oil painting style. Rich impasto texture, visible brushwork, "
        "warm color palette, museum-quality fine art appearance.",
    StyleType.WATERCOLOR:
        "Soft watercolor painting style. Gentle color washes, paper texture, "
        "flowing pigment bleeding, delicate and atmospheric.",
    StyleType.PIXEL:
        "Retro pixel art style. Blocky low-resolution graphics, limited color palette, "
        "nostalgic 8-bit video game aesthetic.",
    StyleType.CYBERPUNK:
        "Cyberpunk dystopian aesthetic. Neon-drenched cityscape, rain-slicked streets, "
        "holographic advertisements, futuristic technology amid urban decay.",
    StyleType.FANTASY:
        "Epic fantasy art style. Magical glowing elements, mythical creatures, "
        "grandiose landscapes, ethereal atmosphere and dramatic scale.",
    StyleType._3D_RENDER:
        "3D computer graphics render. Smooth polygon surfaces, realistic materials, "
        "ray-traced reflections, Pixar-like quality with beautiful lighting.",
    StyleType.MINIMALIST:
        "Clean minimalist style. Simple geometric forms, ample negative space, "
        "restrained color palette, zen-like simplicity and elegance.",
    StyleType.ABSTRACT:
        "Abstract expressive art. Flowing organic shapes, bold color combinations, "
        "non-representational forms, evoking emotion through visual elements.",
    StyleType.REALISTIC:
        "Hyper-realistic style. Photographic accuracy in every detail, "
        "true-to-life textures and proportions, indistinguishable from reality.",
    StyleType.PORTRAIT:
        "Professional portrait style. Flattering lighting on the subject, "
        "clear facial features, soft background blur, magazine-quality composition.",
    StyleType.LANDSCAPE:
        "Breathtaking landscape view. Wide sweeping vista, rich natural details, "
        "atmospheric perspective, immersive environmental storytelling.",
}


@register("dalle")
class DalleStrategy(BaseStrategy):
    """DALL·E 提示词优化策略 — 自然语言描述，与 NBP 库风格一致"""

    platform = PlatformType.DALLE

    @classmethod
    def _detail_chain(cls, creative_level: int) -> str:
        """根据创意程度生成细节链"""
        chains = {
            1: "Keep the description very simple — just the core subject and basic action.",
            2: "Add a few specific details about the subject and setting.",
            3: "Describe the subject, setting, and overall mood in moderate detail.",
            4: "Include subject details, environment, lighting direction, and color palette.",
            5: "Add: subject description, environment, lighting, color palette, and composition.",
            6: "Comprehensive: subject, pose, expression, environment, lighting, color, texture, composition.",
            7: "Rich description: detailed subject, expressive pose, immersive environment, dramatic lighting, specific color scheme, material textures, deliberate composition.",
            8: "Very detailed: precise subject features, clothing textures, layered environment, complex lighting setup, coordinated color palette, multiple material qualities, intentional framing and perspective.",
            9: "Extremely detailed: hyper-specific subject characteristics, intricate clothing with fabric types, multi-zone environment, cinematic lighting with multiple sources, thematic color scheme with accent hues, diverse surface textures, dynamic composition with rule of thirds or golden ratio.",
            10: "Maximum detail: comprehensive subject biography (age, build, expression, precise clothing with colors and materials), multi-element scene with foreground/midground/background layering, complex lighting with key/fill/rim sources, coordinated palette with hex-level precision, varied materials (skin, fabric, metal, glass, water), intentional cinematic composition technique.",
        }
        return chains.get(creative_level, chains[5])

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
        style_desc = _STYLE_DESCRIPTIONS.get(style, "") if style else ""
        detail_chain = cls._detail_chain(creative_level)

        return f"""You are a DALL·E 3 prompt expert. Rewrite the user's input into a high-quality DALL·E prompt.

## DALL·E syntax rules
- DALL·E uses NATURAL LANGUAGE — write flowing descriptive paragraphs
- NO special syntax, NO parameters, NO commas-as-separators
- Style consistency: DALL·E 3 respects detailed style directives
- Aspect ratio is controlled by the API call, NOT the prompt

## Prompt structure (based on 14,000+ community-created image prompts)
Write a flowing, detailed description in THIS order:

1. SUBJECT — Begin with the main subject. Be precise: age, gender, appearance, clothing, pose, expression
   Example: "A young East Asian woman in her mid-20s with waist-length medium-brown hair, wearing a light blue cropped knit cardigan..."

2. ACTION — What is happening? Use specific verbs.
   Example: "She stands in a slight contrapposto pose, holding a smartphone in front of her face..."

3. ENVIRONMENT — Set the scene with detail. Background, furnishings, props, spatial layout.
   Example: "The scene is a bedroom computer corner seen through a wall-mounted mirror. A white desk holds a single monitor showing a soft blue wallpaper..."

4. COLOR PALETTE — Specify dominant and accent colors.
   Example: "The color palette is dominated by blue tones — baby blue, sky blue, and periwinkle — creating a cool, cohesive atmosphere."

5. LIGHTING — Light source, quality, direction.
   Example: "Soft, diffused daylight comes from a large window on the left through sheer curtains, casting gentle shadows."

6. STYLE — Art style directive, texture, mood.
   Example: "Photorealistic style with soft focus on the edges, warm natural tones, magazine-quality composition."

## Style guidance
{style_desc}

## Detail level (creative_level={creative_level}/10)
{detail_chain}

## Quality patterns from community examples
- Use precise color names: "navy blue", "mint green", "lemon yellow", "warm amber"
- Describe EXPRESSIONS in detail: "eyes focused on the central area, expression serious with a slight smile"
- Specify textures: "creamy bokeh background", "smooth porcelain skin", "rough wood grain"
- Use lighting precision: "soft diffused natural light from a large window", "dramatic side lighting"

- Use camera references: "shot on 85mm lens at f/1.8", "shallow depth of field"
- For multi-element scenes, describe each element's position: "on the left side... in the center... in the background..."

## Output rules
1. Output ONLY the prompt — NO explanations, NO labels, NO markdown
2. Write as ONE flowing paragraph of natural language
3. Preserve user's core semantic meaning
4. Match input language (Chinese→Chinese, English→English)
5. Within {max_length} characters
6. {style_text}
{negative_text}"""

    @classmethod
    def post_process(cls, raw_output: str, creative_level: int = 5,
                     preferred_categories: list[str] | None = None) -> str:
        """DALL·E 输出直接使用"""
        text = raw_output.strip().strip('"').strip("'")
        from prompt_engine.keyword_injector import inject_style_keywords; return inject_style_keywords(text, creative_level, preferred_categories)