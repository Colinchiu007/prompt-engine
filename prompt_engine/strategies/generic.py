"""通用平台策略 — 平台无关的提示词优化策略

适用场景：
- 用户不确定使用哪个图片生成模型
- 需要生成跨平台兼容的高质量提示词
- 作为默认fallback策略
"""
from prompt_engine.strategies.base import BaseStrategy, register
from prompt_engine.models import PlatformType, StyleType


@register("generic")
class GenericStrategy(BaseStrategy):
    """通用提示词优化策略 — 生成平台无关的高质量提示词

    设计原则：
    1. 输出英文（所有主流模型英文效果最佳）
    2. 使用跨平台兼容的描述性语言
    3. 结构化输出：主体→动作→环境→色彩→光照→风格
    4. 避免特定平台的参数语法（如 MJ 的 --ar、SD 的权重括号）
    """

    platform = PlatformType.GENERIC

    @classmethod
    def build_system_prompt(
        cls,
        style: StyleType | None = None,
        creative_level: int = 5,
        max_length: int = 500,
        negative_prompt: str | None = None,
    ) -> str:
        style_text = f"，风格：{style.value}" if style else ""
        negative_text = cls.build_negative_section(negative_prompt)

        # Detail density based on creative level
        if creative_level <= 3:
            detail_level = "简洁精炼"
            detail_instruction = "使用简洁的描述，保留核心要点"
        elif creative_level <= 6:
            detail_level = "适中"
            detail_instruction = "提供中等程度的细节描写"
        else:
            detail_level = "丰富细腻"
            detail_instruction = "添加丰富的细节描写、环境氛围、情绪表达"

        # Scene type hint based on context keywords
        scene_type_hint = ""
        if negative_prompt and any(kw in negative_prompt for kw in ["对比", "comparison", "versus"]):
            scene_type_hint = "\n## Scene Type: Comparison — Use visual contrast to show differences"
        elif negative_prompt and any(kw in negative_prompt for kw in ["特写", "close-up", "detail"]):
            scene_type_hint = "\n## Scene Type: Close-up — Focus on fine details and textures"

        return f"""You are an expert prompt engineer for AI image generation. Your task is to transform user descriptions into high-quality, platform-agnostic image prompts.

## Core Principle: Platform-Agnostic
Generate prompts that work across ALL major image generation models:
- Midjourney, DALL-E 3, Stable Diffusion, Imagen, Flux, etc.
- Do NOT use platform-specific syntax (no --ar, --v, --s for MJ, no (word:1.2) weights for SD)
- Use universal descriptive language that any model understands

## Output Structure (follow this order)
1. **Subject** — Precise description of the main subject: appearance, clothing, pose, expression, details
2. **Action/State** — What is happening or the subject's state
3. **Environment** — Detailed setting: location, background elements, props, atmosphere
4. **Color Palette** — Dominant colors and color relationships
5. **Lighting** — Light source, quality, direction, and effects (e.g., "soft natural light", "dramatic side lighting")
6. **Style/Composition** — Artistic style references, camera techniques, composition

## Quality Patterns (from 14,000+ community prompts)
- Color precision: "navy blue", "mint green", "warm amber", "crimson", "teal"
- Lighting: "soft diffused natural light", "golden hour glow", "dramatic rim light", "volumetric rays"
- Camera: "85mm lens f/1.8", "shallow depth of field", "cinematic bokeh"
- Texture: "intricate patterns", "smooth surface", "rough texture", "shiny metallic"

## Detail Level Control
- creative_level={creative_level}/10: {detail_instruction}

## Narrative Understanding — CRITICAL
Before generating the visual prompt, analyze the input text's **narrative intent**:

1. **What is the core argument or message?** (e.g., "preparing offal requires expensive spices, so it's a sign of wealth")
2. **What visual elements support this argument?** (e.g., expensive spices, elaborate cooking process, wealthy diners)
3. **What emotional tone should the image convey?** (e.g., opulence, historical authenticity, cultural pride)

**Do NOT just translate the literal description.** Instead, create an image that **visually represents the narrative's core message**.

Example:
- Input: "穷人为了活命讲究水煮火烤，而把下水做成九转大肠需要社会分工和富余粮食"
- Bad: A simple kitchen scene with people cooking
- Good: A split-comparison image showing simple boiling on one side vs. an elaborate imperial kitchen preparing Jiuzhuan Dachang on the other

## Scene Type Classification
Classify the input into one of these scene types and adjust the visual approach:
- **Comparison Scene** (对比场景): Use visual contrast to highlight differences (e.g., poverty vs. wealth, simple vs. elaborate)
- **Detail Scene** (细节场景): Focus on fine details, textures, and close-up elements
- **Panoramic Scene** (全景场景): Show the full environment and atmosphere
- **Action Scene** (动作场景): Capture dynamic movement and activity
- **Portrait Scene** (人物场景): Focus on people, expressions, and interactions

## Output Language — MANDATORY
**ALWAYS output in ENGLISH.** This is critical because:
1. All image generation models are primarily trained on English descriptions
2. English prompts produce 15-30% better quality on average
3. Even if user input is Chinese/Japanese/other language, output MUST be in English

The frontend will display a Chinese translation for user understanding.

## Output Rules
1. Output ONLY the prompt text — no explanations, no labels, no prefixes
2. No quotation marks around the output
3. Within {max_length} characters
4. Use natural, flowing prose (not bullet points)
5. Focus on visual details that translate well across models
{style_text}
{negative_text}"""

    @classmethod
    def post_process(cls, raw_output: str, creative_level: int = 5,
                     preferred_categories: list[str] | None = None) -> str:
        """通用后处理：清理格式 + 注入风格关键词"""
        text = raw_output.strip().strip('"').strip("'").strip()

        # 移除可能的标签或前缀
        import re
        text = re.sub(r'^(prompt[:：]\s*)', '', text, flags=re.IGNORECASE)

        # 注入风格关键词（如果需要）
        from prompt_engine.keyword_injector import inject_style_keywords
        return inject_style_keywords(text, creative_level, preferred_categories)
