"""Prompt building — template rendering + system prompt construction.

Extracted from optimizer.py God Class refactoring (Phase 1).
"""

from typing import Optional

from prompt_engine.models import OptimizeRequest, OptimizeResult
from prompt_engine.strategies import get_strategy


class PromptBuilder:
    """提示词构建：模板渲染 + 系统提示词 + 上下文注入"""

    @staticmethod
    def render_from_template(request: OptimizeRequest) -> OptimizeResult:
        """确定性模板直出；creative_level 只控制细节密度，不决定是否调用 LLM。"""
        strategy_cls = get_strategy(request.platform.value)
        if not strategy_cls:
            strategy_cls = get_strategy("generic")

        cl = max(1, min(10, request.creative_level))

        # 基础块：用户 prompt 就是主体
        parts = [request.prompt]

        quality_tags = {
            2: "clean visual description",
            3: "balanced visual detail",
            4: "detailed visual description",
            5: "refined visual detail",
            6: "cinematic composition and atmosphere",
            7: "layered environment and emotional tone",
            8: "historical authenticity and coherent spatial storytelling",
            9: "intricate environmental, material, and lighting details",
            10: "highly detailed visual storytelling with precise composition",
        }
        if cl >= 2:
            parts.append(quality_tags[cl])

        # Level 3+: 稳定光影描述；模板路径不应以随机词制造“重新生成”的假象。
        if cl >= 3:
            lighting = {
                3: "soft lighting",
                4: "natural light",
                5: "warm glow",
                6: "bright daylight",
                7: "natural light",
                8: "soft lighting",
                9: "warm glow",
                10: "bright daylight",
            }[cl]
            parts.append(lighting)
        raw = ", ".join(parts)
        # 策略后处理只负责平台格式；以 level 1 调用可跳过其随机风格关键词注入。
        # 模板自身已按 cl 注入稳定的细节密度，不能再次引入随机性。
        final = strategy_cls.post_process(raw, creative_level=1)

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
        if context.get("narrative_intent"):
            parts.append(f"Narrative intent/文案意图: {context['narrative_intent'][:300]}")
        if context.get("scene_type"):
            parts.append(f"Scene type/场景类型: {context['scene_type']}")
        if context.get("full_text"):
            # 完整文案摘要（用于理解上下文），限制长度避免 token 爆炸
            full_text = context['full_text'][:500]
            parts.append(f"Full text context/完整文案上下文: {full_text}")

        if not parts:
            return ""

        section = "\n\n## Character consistency / 角色一致性\n"
        section += "\n".join(parts)
        section += "\n- Keep the same character identity (appearance/服装/发型) across all images where the same name appears."
        section += "\n- 相同名字的角色在所有图片中保持同一身份（外貌、服装、发型一致）。"
        return section
