"""视频提示词构建：system prompt + context 注入 + 关键词维度提示（独立实现）。"""
from __future__ import annotations

from typing import Optional

from video_prompt_engine.models import VideoOptimizeRequest
from video_prompt_engine.strategies import get_strategy


class VideoPromptBuilder:
    @staticmethod
    def build_system_prompt(
        strategy_cls,
        style: Optional[str],
        creative_level: int,
        max_length: int,
        negative_prompt: Optional[str] = None,
        keywords_hint: str = "",
        output_language: str = "en",
        tier: str = "batch",
    ) -> str:
        return strategy_cls.build_system_prompt(
            style=style,
            creative_level=creative_level,
            max_length=max_length,
            negative_prompt=negative_prompt,
            keywords_hint=keywords_hint,
            output_language=output_language,
            tier=tier,
        )

    @staticmethod
    def build_context_section(context: Optional[dict]) -> str:
        if not context:
            return ""
        parts = []
        if context.get("setting"):
            parts.append(f"Setting/场景: {context['setting']}")
        if context.get("character"):
            c = context["character"]
            name = c.get("name", "") if isinstance(c, dict) else str(c)
            parts.append(f"Current character/当前角色: {name}")
        if context.get("character_list"):
            names = [c.get("name", "") if isinstance(c, dict) else str(c) for c in context["character_list"]]
            parts.append(f"All characters/全部角色: {', '.join(names)}")
        if context.get("synopsis"):
            parts.append(f"Story synopsis/故事梗概: {str(context['synopsis'])[:200]}")
        if context.get("narrative_intent"):
            parts.append(f"Narrative intent/文案意图: {str(context['narrative_intent'])[:300]}")
        if context.get("scene_type"):
            parts.append(f"Scene type/场景类型: {context['scene_type']}")
        if context.get("full_text"):
            parts.append(f"Full text context/完整文案上下文: {str(context['full_text'])[:500]}")
        if not parts:
            return ""
        section = "\n\n## Video Fact-Fidelity Context / 视频事实保真上下文\n"
        section += "\n".join(parts)
        section += "\n- Keep the same subject identity, era/setting and core events consistent with the context."
        return section
