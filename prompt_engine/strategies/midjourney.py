"""Midjourney 平台策略 — 从 Nano Banana Pro + MJ Style Reference 库提取的提示词模式。

MJ Style Reference 数据库:
- 27 个风格维度，2100+ 专业关键词
- 覆盖: 光照/材质/色彩/镜头/构图/自然/艺术媒介/文化风格/影视参考
- 来源: github.com/willwulfken/MidJourney-Styles-and-Keywords-Reference
"""
import json
import os
import random
import re
from pathlib import Path

from prompt_engine.strategies.base import BaseStrategy, register
from prompt_engine.models import PlatformType, StyleType


# 风格 → Midjourney 参数映射
_STYLE_AR_MAP = {
    StyleType.PORTRAIT: "3:4",
    StyleType.PHOTOGRAPHY: "4:3",
    StyleType.ANIME: "16:9",
    StyleType.LANDSCAPE: "16:9",
    StyleType.REALISTIC: "4:3",
    StyleType.CARTOON: "1:1",
    StyleType.OIL_PAINTING: "4:3",
    StyleType.WATERCOLOR: "4:3",
    StyleType.PIXEL: "1:1",
    StyleType.CYBERPUNK: "16:9",
    StyleType.FANTASY: "16:9",
    StyleType._3D_RENDER: "16:9",
    StyleType.MINIMALIST: "1:1",
    StyleType.ABSTRACT: "16:9",
}

# 风格 → 版本风格参数
_STYLE_VERSION = {
    StyleType.ANIME: " --style expressive",
    StyleType.CARTOON: " --style expressive",
    StyleType.FANTASY: " --style expressive",
    StyleType.PHOTOGRAPHY: " --style raw",
    StyleType.REALISTIC: " --style raw",
    StyleType.PORTRAIT: " --style raw",
    StyleType.OIL_PAINTING: "",
    StyleType.WATERCOLOR: "",
    StyleType.CYBERPUNK: " --style expressive",
    StyleType._3D_RENDER: "",
    StyleType.MINIMALIST: " --style raw",
    StyleType.ABSTRACT: "",
    StyleType.PIXEL: "",
}

# 质量修饰词（源自 NBP 库高频词）
_QUALITY_MODIFIERS = {
    1: "",
    2: "simple style",
    3: "clean composition, minimalist",
    4: "detailed, well-composed",
    5: "detailed, well-composed, professional lighting",
    6: "highly detailed, professional lighting, beautiful composition",
    7: "highly detailed, dramatic lighting, stunning composition, sharp focus",
    8: "intricately detailed, cinematic lighting, masterful composition, 8k",
    9: "hyper-detailed, volumetric lighting, award-winning composition, 8k, HDR",
    10: "hyper-detailed, cinematic volumetric lighting, award-winning masterpiece composition, 8k, HDR, trending on artstation",
}


@register("midjourney")
class MidjourneyStrategy(BaseStrategy):
    """Midjourney 提示词优化策略 — 基于社区高质量 prompt 模式"""

    platform = PlatformType.MIDJOURNEY

    @classmethod
    def _style_prompt_block(cls, style: StyleType | None) -> str:
        """生成风格描述块（NBP 库的风格词汇）"""
        if not style:
            return ""
        blocks = {
            StyleType.PHOTOGRAPHY:
                "Photorealistic, professional photography style. "
                "Include lens specification, aperture, and lighting details.",
            StyleType.PORTRAIT:
                "Professional portrait photography style. "
                "Include lighting setup, lens choice (85mm preferred), "
                "depth of field, and background treatment.",
            StyleType.ANIME:
                "Anime/manga illustration style. "
                "Clean linework, cel shading, vibrant colors, "
                "expressive character design characteristic of Japanese animation.",
            StyleType.CARTOON:
                "Cartoon illustration style. "
                "Bold outlines, exaggerated features, flat color blocks, "
                "whimsical and approachable aesthetic.",
            StyleType.OIL_PAINTING:
                "Oil painting style. "
                "Visible brushstrokes, rich texture, impasto technique, "
                "classical painterly quality with depth and warmth.",
            StyleType.WATERCOLOR:
                "Watercolor painting style. "
                "Soft washes, blending edges, paper texture visible, "
                "translucent color layers with gentle bleeding effects.",
            StyleType.PIXEL:
                "Pixel art style, 8-bit aesthetic. "
                "Blocky low-resolution rendering with limited color palette, "
                "nostalgic retro game visual quality.",
            StyleType.CYBERPUNK:
                "Cyberpunk / sci-fi aesthetic. "
                "Neon lighting (cyan, magenta, purple), rain-slicked surfaces, "
                "futuristic cityscape, holographic elements, high contrast.",
            StyleType.FANTASY:
                "Fantasy / epic aesthetic. "
                "Dramatic lighting, ethereal atmosphere, magical elements, "
                "otherworldly landscapes, grand scale composition.",
            StyleType._3D_RENDER:
                "3D rendered style, Octane render. "
                "PBR materials, ray-traced lighting, smooth surfaces, "
                "clean geometry, photorealistic CG quality.",
            StyleType.MINIMALIST:
                "Minimalist style. "
                "Clean lines, negative space, simple color palette "
                "(monochrome or limited hues), uncluttered composition.",
            StyleType.ABSTRACT:
                "Abstract art style. "
                "Geometric or organic shapes, flowing forms, "
                "expressive color combinations, non-representational composition.",
            StyleType.REALISTIC:
                "Hyper-realistic style. "
                "True-to-life textures, accurate proportions, "
                "natural lighting that mimics real-world physics.",
        }
        return blocks.get(style, "")

    @classmethod
    def _camera_block(cls, creative_level: int) -> str:
        """生成镜头参数块（源自 NBP 库高频摄影术语）"""
        if creative_level < 4:
            return "Simple clear view of the subject."
        options = [
            "Shot on 85mm lens at f/1.8, shallow depth of field, creamy bokeh background.",
            "Shot on 50mm lens at f/2.8, balanced depth of field, natural perspective.",
            "Shot on 35mm lens at f/2.0, wide environmental context, slight distortion.",
            "Shot on 24-70mm zoom at f/4, versatile framing, sharp throughout.",
            "Macro shot, extreme close-up, revealing fine textures and details.",
            "Shot on 85mm lens at f/1.4, ultra-shallow DOF, dreamy bokeh.",
            "Shot on 135mm lens at f/2.0, compressed perspective, subject isolation.",
            "Shot on 16mm ultra-wide, dramatic perspective, environmental storytelling.",
        ]
        idx = creative_level % len(options)
        return options[idx]

    @classmethod
    def _lighting_block(cls, creative_level: int) -> str:
        """生成光照描述块（源自 NBP 库高频光照术语）"""
        if creative_level < 3:
            return "Even, flat lighting."
        options = [
            "Soft, diffused natural light from a large window, gentle shadows.",
            "Dramatic side lighting, strong contrasts, deep shadows.",
            "Golden hour warm light, long soft shadows, warm amber tones.",
            "Cinematic chiaroscuro lighting, high contrast, film noir atmosphere.",
            "Ring light setup, clean even illumination, beauty lighting.",
            "Rim lighting from behind, glowing edge highlights, silhouette effect.",
            "Volumetric lighting, visible light rays, atmospheric depth.",
            "Multi-light studio setup, key light + fill light + backlight, professional finish.",
            "Neon ambient lighting, colorful light spills, cyberpunk atmosphere.",
            "Candlelit warm glow, intimate atmosphere, flickering shadows.",
        ]
        idx = (creative_level * 3) % len(options)
        return options[idx]

    @classmethod
    def _composition_block(cls, creative_level: int) -> str:
        """生成构图描述块（源自 NBP 库构图模式）"""
        if creative_level < 4:
            return ""
        options = [
            "Rule of thirds composition.",
            "Centered composition with symmetrical balance.",
            "Leading lines guiding the eye to the subject.",
            "Dynamic diagonal composition, Dutch angle.",
            "Foreground framing, layered depth throughout the image.",
            "Golden ratio spiral composition, naturally guiding the viewer's eye.",
            "Bird's eye view perspective, looking down on the scene.",
            "Low angle shot, looking up at the subject, making it appear powerful.",
        ]
        idx = (creative_level * 7) % len(options)
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

        ar = _STYLE_AR_MAP.get(style, "16:9") if style else "16:9"
        style_ver = _STYLE_VERSION.get(style, "") if style else ""
        stylize_val = creative_level * 50
        quality_mod = _QUALITY_MODIFIERS.get(creative_level, "detailed")

        style_block = cls._style_prompt_block(style)
        camera_block = cls._camera_block(creative_level)
        lighting_block = cls._lighting_block(creative_level)
        composition_block = cls._composition_block(creative_level)

        return f"""You are a Midjourney prompt expert. Rewrite the user's input into a high-quality Midjourney prompt.

## Platform syntax
CRITICAL: Append `--ar {ar} --v 6.1 --s {stylize_val}{style_ver}` at the end.

Parameter guide:
- --ar = aspect ratio. Use {ar} for this style (16:9/4:3/1:1/3:4/9:16)
- --v 6.1 = Midjourney version
- --s = stylization (0-1000). Use {stylize_val} (creative_level x 50)
- --style raw = photographic/realistic output
- --style expressive = artistic/illustrative output
- NEVER use --iw or --no

## Prompt structure (from 14,000+ community prompts + MJ Style Reference analysis)
Build as a DETAILED FLOWING DESCRIPTION in this order:

1. [Subject] — age, gender, appearance, clothing, pose, expression
2. [Action] — specific verbs describing what's happening
3. [Environment] — detailed background, furnishings, props
4. [Color palette] — dominant and accent colors
5. [Lighting] — {lighting_block}
6. [Camera/Composition] — {camera_block} {composition_block}
7. [Quality] — {quality_mod}
8. --ar {ar} --v 6.1 --s {stylize_val}{style_ver}

## Style
{style_block}

## MJ Style Reference Categories (use freely based on creative_level {creative_level})
You have access to 2,100+ style keywords across 27 dimensions.
Pick the most relevant ones naturally:
- **Lighting**: Volumetric Lighting, Cinematic Lighting, Rembrandt Lighting, Godrays, Flare, etc.
- **Materials**: Matte, Glossy, Rough, Translucent, Metallic, Textured surfaces
- **Colors**: Analogous Colors, High Saturation, Warm Color Palette, Complementary Colors
- **Camera**: Award Winning Photography, Shallow DOF, Cinematic, Filmic, Portrait
- **Design**: Minimalist, Hyperdetailed, Ornate, Flat Design, Neo, Art Deco
- **Nature**: Natural landscapes, organic textures, organic forms
- **Effects**: Chromatic Aberration, Ray Tracing, Barrell Distortion, Depth of Field
- **Art Mediums**: Watercolor, Oil Painting, Digital Art, Sketch, Print
- **Perspective**: One-Point, Isometric, Wide Shot, Closeup, Rule of Thirds
- **Themes**: Punk, Cyberpunk, Fantasy, Retro, Futuristic, Atmospheric

## Quality rules (from community patterns)
- Camera terms: "85mm", "f/1.8", "shallow DOF", "bokeh"
- Lighting terms: "soft diffused", "dramatic side", "golden hour", "rim light", "volumetric"
- Texture words: "intricate", "detailed texture", "material quality"
- Color precision: "navy blue", "mint green", "warm amber tones"
- Expression: "serious, with a slight smile", "focused and expectant"

## Output rules
1. Output ONLY the prompt — NO explanations, NO labels
2. Preserve user's core semantic
3. Match input language (Chinese->Chinese, English->English)
4. Within {max_length} characters
5. {style_text}
{negative_text}"""

    @classmethod
    def post_process(cls, raw_output: str, creative_level: int = 5) -> str:
        text = raw_output.strip().strip('"').strip("'")
        if "--ar " not in text:
            text += " --ar 16:9 --v 6.1 --s 250"
        # MJ Style Reference 关键词注入
        return _inject_style_keywords(text, creative_level)


# ============================================================================
# MJ Style Reference 数据库集成
# ============================================================================

# 全局缓存：加载一次，跨实例共享
_MJ_STYLE_DB: dict | None = None


def _load_mj_style_db() -> dict | None:
    """加载 MJ 风格关键词数据库（懒加载）。"""
    global _MJ_STYLE_DB
    if _MJ_STYLE_DB is not None:
        return _MJ_STYLE_DB
    db_path = Path(__file__).parent.parent / "data" / "mj_style_final.json"
    if db_path.exists():
        try:
            with open(db_path, "r", encoding="utf-8") as f:
                _MJ_STYLE_DB = json.load(f)
            return _MJ_STYLE_DB
        except Exception:
            pass
    return None


def _inject_style_keywords(prompt: str, creative_level: int = 5) -> str:
    """从 MJ 风格数据库随机注入风格关键词到 prompt。

    从 27 个风格维度中根据创意等级选择维度：
    - 低创意(1-3): 注入 1-2 个基础关键词（光照/材质）
    - 中创意(4-6): 注入 2-3 个关键词（+ 色彩/镜头）
    - 高创意(7-10): 注入 3-5 个关键词（+ 文化/艺术媒介/影视）

    每个关键词从同义词组中随机选取，保持多样性。
    过滤掉短噪音词（<=3字符）和技术缩写。
    """
    db = _load_mj_style_db()
    if not db:
        return prompt

    if creative_level <= 3:
        cats = ["Lighting", "Material_Properties"]
        num = random.randint(1, 2)
    elif creative_level <= 6:
        cats = ["Lighting", "Material_Properties", "Colors_and_Palettes", "Camera"]
        num = random.randint(2, 3)
    else:
        cats = [
            "Lighting", "Material_Properties", "Colors_and_Palettes", "Camera",
            "Design_Styles", "Nature_and_Animals", "Themes",
            "SFX_and_Shaders", "Perspective", "Drawing_and_Art_Mediums",
        ]
        num = random.randint(3, 5)

    inject_kws = []
    chosen_cats = random.sample(cats, min(num, len(cats)))
    for cat in chosen_cats:
        kws = db.get(cat, [])
        # 过滤：只保留有实际美学意义的词
        # 排除纯缩写/噪音/纯数字
        NOISE_WORDS = {"LED", "LCD", "UV", "CRT", "CFL", "OLED", "AMOLED", "HDR", "RGB", "CMYK"}
        good = []
        for k in kws:
            upper = k.upper()
            # 排除含噪声缩写词
            if any(nw in upper for nw in NOISE_WORDS):
                continue
            # 排除纯数字（含全角数字等）
            if all(c.isdigit() for c in k):
                continue
            # 保留：>=4字符 或 含空格/连字符（多词组合）
            if len(k) >= 4 or " " in k or "-" in k or "\u00a0" in k:
                good.append(k)
        if good:
            inject_kws.append(random.choice(good))

    if inject_kws:
        injected = ", " + ", ".join(inject_kws)
        return prompt.rstrip(",. ") + injected + "."

    return prompt
