"""Prompt building — template rendering + system prompt construction.

Extracted from optimizer.py God Class refactoring (Phase 1).
"""

from random import choice
from typing import Optional

from prompt_engine.models import OptimizeRequest, OptimizeResult
from prompt_engine.strategies import get_strategy


class PromptBuilder:
    """提示词构建：模板渲染 + 系统提示词 + 上下文注入"""

    @staticmethod
    def render_from_template(request: OptimizeRequest) -> OptimizeResult:
        """低创意等级（≤3）用模板直出，不调 LLM"""
        strategy_cls = get_strategy(request.platform.value)
        if not strategy_cls:
            strategy_cls = get_strategy("generic")

        cl = max(1, min(3, request.creative_level))

        # 基础块：用户 prompt 就是主体
        parts = [request.prompt]

        # Level 2+: 质量标签
        if cl >= 2:
            quality_tags = ["simple", "clean", "medium", "detailed", "refined"]
            parts.append(quality_tags[min(cl - 1, len(quality_tags) - 1)])

        # Level 3: 简单光影描述
        if cl >= 3:
            lighting = choice(["soft lighting", "natural light", "warm glow", "bright daylight"])
            parts.append(lighting)

        raw = ", ".join(parts)
        final = strategy_cls.post_process(raw, creative_level=cl)

        return OptimizeResult(
            optimized_prompt=final,
            platform=request.platform,
            style=request.style,
            model_used="template",
            tokens_used=0,
            duration_ms=0,
            error=None,
        )

    @staticmethod
    def build_system_prompt(
        strategy_cls,
        style: Optional[str],
        creative_level: int,
        max_length: int,
        negative_prompt: Optional[str] = None,
    ) -> str:
        """构建系统提示词"""
        return strategy_cls.build_system_prompt(
            style=style,
            creative_level=creative_level,
            max_length=max_length,
            negative_prompt=negative_prompt,
        )

    @staticmethod
    def build_context_section(context: Optional[dict]) -> str:
        """PROJECT-012 上下文注入（角色一致性）"""
        if not context:
            return ""

        parts = []
        if context.get("setting"):
            parts.append(f"Setting/场景: {context['setting']}")
        if context.get("character"):
            parts.append(f"Current character/当前角色: {context['character'].get('name', '')}")
        if context.get("character_list"):
            names = [c["name"] for c in context["character_list"] if "name" in c]
            parts.append(f"All characters/全部角色: {', '.join(names)}")
        if context.get("synopsis"):
            parts.append(f"Story synopsis/故事梗概: {context['synopsis'][:200]}")

        if not parts:
            return ""

        section = "\n\n## Character consistency / 角色一致性\n"
        section += "\n".join(parts)
        section += "\n- Keep the same character identity (appearance/服装/发型) across all images where the same name appears."
        section += "\n- 相同名字的角色在所有图片中保持同一身份（外貌、服装、发型一致）。"
        return section
