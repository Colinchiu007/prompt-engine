"""Seedance 平台策略 — 即梦 Seedance 2.0 视频提示词撰写（来自 dexhunter/seedance2-skill 思路）。

要点：
- @ 引用语法（多模态素材用途指定）
- 多模态输入约束（图片 ≤9、视频 ≤3、音频 ≤3、总文件 ≤12）
- 运镜复刻 / 特效模仿 / 音乐卡点 / 电商广告 / 短剧创作
- Fact-Fidelity 保真
"""
from __future__ import annotations

from typing import Optional

from video_prompt_engine.models import VideoPlatformType
from video_prompt_engine.strategies.base import BaseVideoStrategy, register


@register("seedance")
class SeedanceStrategy(BaseVideoStrategy):
    """Seedance 2.0 专项策略（@引用语法 + 多模态约束）。"""

    platform = VideoPlatformType.SEEDANCE

    @classmethod
    def build_system_prompt(
        cls,
        style: Optional[str] = None,
        creative_level: int = 5,
        max_length: int = 500,
        negative_prompt: Optional[str] = None,
        keywords_hint: str = "",
        output_language: str = "en",
    ) -> str:
        style_text = f"，风格：{style}" if style else ""
        negative_text = cls.build_negative_section(negative_prompt)
        keywords = f"\n## 视频关键词参考\n{keywords_hint}" if keywords_hint else ""
        lang_section = cls.build_language_section(output_language)
        return f"""You are a Seedance 2.0 prompt engineer (ByteDance multimodal AI video model).

## Multimodal Input Constraints
- Images: ≤9 (jpeg/png/webp/bmp/tiff/gif, each <30MB); Videos: ≤3 (mp4/mov, each <50MB, 2-15s); Audio: ≤3 (mp3/wav, each <15MB, ≤15s); Total files ≤12.
- Output duration 4-15s; built-in SFX/music; 480p-720p.

## @ Reference Syntax (MANDATORY when referencing media)
- Use `@` to specify each asset's role, e.g. "@image1 作为角色参考，@video2 复刻运镜".
- Camera-motion replication / effect imitation / music beat sync / e-commerce ad / short drama are supported scenarios.

## Fact-Fidelity (MANDATORY)
- Do NOT change the subject's identity, era/setting, or event facts from the input.

## Output Structure
Follow the six-element structure (Subject / Action / Environment / Colors / Lighting / Style+Shot+Camera) and output the single-string video prompt within {max_length} chars.
{keywords}{lang_section}
## Output Format (MANDATORY)
Output ONLY a JSON object with exactly: prompt / shot / camera / motion_intensity / scene_transition / continuity_token / duration_hint. No extra text.
{style_text}
{negative_text}"""
