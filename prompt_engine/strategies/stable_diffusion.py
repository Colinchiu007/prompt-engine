"""Stable Diffusion 平台策略 — 带权重语法和负面提示词"""
from prompt_engine.strategies.base import BaseStrategy, register
from prompt_engine.models import PlatformType, StyleType


# 不同风格的质量前缀词
_QUALITY_PREFIX = {
    StyleType.PHOTOGRAPHY: "photorealistic, professional photo, raw photo, (sharp focus:1.2), (detailed skin texture:1.1)",
    StyleType.REALISTIC: "photorealistic, hyperrealistic, (masterpiece:1.2), (best quality:1.2), (highres:1.1)",
    StyleType.ANIME: "anime style, (masterpiece:1.2), (best quality:1.2), vibrant colors, cel shading",
    StyleType.CARTOON: "cartoon style, cel shaded, bold outlines, flat colors, vibrant",
    StyleType.OIL_PAINTING: "oil painting, (impasto:1.1), rich texture, visible brushstrokes, painterly",
    StyleType.WATERCOLOR: "watercolor painting, soft washes, paper texture, (translucent:1.1), bleeding edges",
    StyleType.PIXEL: "pixel art, (8-bit:1.1), retro game art, blocky, limited palette",
    StyleType.CYBERPUNK: "cyberpunk, neon, dystopian, sci-fi, (glowing:1.1), rain, reflections",
    StyleType.FANTASY: "fantasy art, ethereal, magical, epic, (detailed:1.2), (intricate:1.1)",
    StyleType._3D_RENDER: "3d render, octane render, (pbr:1.1), ray tracing, (smooth:1.1), clean geometry",
    StyleType.MINIMALIST: "minimalist, clean, simple, geometric, flat design, (negative space:1.2)",
    StyleType.ABSTRACT: "abstract art, geometric, fluid, expressive, colorful, non-representational",
}

# 风格对应的负面提示词
_NEGATIVE_PROMPTS = {
    StyleType.PHOTOGRAPHY: "cartoon, illustration, painting, 3d render, anime, oversaturated, blurry",
    StyleType.REALISTIC: "cartoon, illustration, 3d render, painting, anime, low quality, blurry, distorted",
    StyleType.ANIME: "photorealistic, 3d, realistic, (worst quality:1.2), low quality, bad anatomy",
    StyleType.CARTOON: "photorealistic, 3d render, realistic, detailed texture, complex shading, dark",
    StyleType.OIL_PAINTING: "photorealistic, cartoon, digital art, flat, pixel art, low detail, sketchy",
    StyleType.WATERCOLOR: "oil painting, thick impasto, photorealistic, digital art, sharp edges, cartoon",
    StyleType.PIXEL: "photorealistic, smooth, high resolution, detailed texture, 3d, complex shading",
    StyleType.CYBERPUNK: "bright daylight, sunny, cheerful, natural, rural, low contrast, pastel colors",
    StyleType.FANTASY: "photorealistic, modern, mundane, everyday, low contrast, gray, drab",
    StyleType._3D_RENDER: "cartoon, flat, 2d, oil painting, watercolor, low resolution, blurry, pixelated",
    StyleType.MINIMALIST: "cluttered, busy, complex, detailed, photorealistic, colorful, ornate",
    StyleType.ABSTRACT: "photorealistic, cartoon, 3d render, simple, minimalist, black and white",
    None: "nsfw, lowres, bad anatomy, bad hands, text, error, missing fingers, extra digit, fewer digits, cropped, worst quality, low quality, normal quality, jpeg artifacts, signature, watermark, username, blurry",
}


@register("stable_diffusion")
class StableDiffusionStrategy(BaseStrategy):
    """Stable Diffusion 提示词优化策略 — SDXL/SD3 权重语法"""

    platform = PlatformType.STABLE_DIFFUSION

    @classmethod
    def _style_prompt_block(cls, style: StyleType | None) -> str:
        """生成风格前缀词"""
        if style and style in _QUALITY_PREFIX:
            return _QUALITY_PREFIX[style]
        return "(masterpiece:1.2), (best quality:1.2), (highres:1.1), (8k:1.1)"

    @classmethod
    def _negative_prompt(cls, style: StyleType | None) -> str:
        """生成负面提示词"""
        neg = _NEGATIVE_PROMPTS.get(style, _NEGATIVE_PROMPTS[None])
        return neg

    @classmethod
    def _lighting_tags(cls, creative_level: int) -> str:
        """光照关键词"""
        if creative_level < 3:
            return "ambient light"
        options = [
            "(natural lighting:1.2), (soft light:1.1)",
            "(dramatic lighting:1.3), (chiaroscuro:1.2)",
            "(golden hour:1.3), (sunlight:1.2), (warm tones:1.1)",
            "(cinematic lighting:1.3), (volumetric light:1.2)",
            "(studio lighting:1.2), (ring light:1.1)",
            "(rim light:1.3), (backlight:1.2), (silhouette:1.1)",
            "(neon light:1.3), (glowing:1.2), (colorful light:1.1)",
            "(candlelight:1.2), (warm glow:1.3), (cozy atmosphere:1.1)",
        ]
        idx = (creative_level * 3) % len(options)
        return options[idx]

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
        quality_prefix = cls._style_prompt_block(style)
        negative = cls._negative_prompt(style)
        lighting = cls._lighting_tags(creative_level)

        return f"""You are a Stable Diffusion prompt expert. Rewrite the user's input into a high-quality SD prompt.

## CRITICAL syntax rules
SD uses comma-separated keyword format with weight syntax:
  - Boost: `(keyword:1.2)` or `(keyword:1.3)` (1.0-1.5 range; 1.3+ is strong)
  - Weaken: `(keyword:0.8)` or `(keyword:0.5)`
  - Quality prefix: START every prompt with high-quality keywords
  - Order: most important concepts FIRST, least important LAST
  - Separate concepts with commas — NO flowing sentences, NO periods

## Prompt structure
Build in EXACTLY this order:

[Quality prefix] → [Subject] → [Details] → [Environment] → [Lighting] → [Style] → [Composition] → [Technical specs]

1. START with: {quality_prefix}
2. Subject: precise appearance, clothing, pose, expression
3. Details: specific features, accessories, textures
4. Environment: setting, background, props
5. Lighting: {lighting}
6. Style/Color: art style, color palette
7. Composition: angle, framing, perspective
8. Technical: aspect ratio tag (e.g., --ar 16:9 or :16:9)

## Negative prompt
ALWAYS include this negative prompt internally:
{negative}

## Style guidance
{style_text}

## Keyword quality rules (from community prompt patterns)
- Use texture descriptors: "intricate", "detailed texture", "smooth", "rough", "shiny"
- Use color precision: "navy blue", "mint green", "burgundy", "teal"
- Use material words: "velvet", "leather", "metal", "glass", "wood", "marble"
- Use camera terms when appropriate: "85mm", "f/1.8", "bokeh", "depth of field"
- Use expression detail: "smiling warmly", "serious expression", "looking at viewer"

## Output rules
1. Output ONLY the prompt keywords — NO explanations, NO labels
2. ALWAYS use English output (SD works best with English)
3. Comma-separated keyword format ONLY — NO full sentences
4. Words ordered by importance descending
5. Each important quality/concept should have weight applied
6. Within {max_length} characters
7. {style_text}
{negative_text}"""

    @classmethod
    def post_process(cls, raw_output: str, creative_level: int = 5,
                     preferred_categories: list[str] | None = None) -> str:
        text = raw_output.strip().strip('"').strip("'")
        # 确保不以句号结尾（SD 用逗号分割）
        if text.endswith("."):
            text = text[:-1]
        # 确保逗号分隔
        if ", " not in text and len(text) > 20:
            # 可能是句子格式，尝试逗号化
            pass
        return text