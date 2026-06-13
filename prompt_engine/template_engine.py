"""Prompt-as-Code 模板引擎

将 prompt 拆解为可组合的原子块（主体/光影/材质/构图等），
支持模板化渲染、参数池随机选择、创意等级控制。

与 awesome-gpt-image-2 的 Prompt-as-Code 哲学对齐。
"""
import random
from dataclasses import dataclass, field
from typing import Optional

from prompt_engine.models import StyleCategory


@dataclass
class PromptBlock:
    """一个可组合的原子化 prompt 块。

    Example:
        pb = PromptBlock(
            name="subject",
            template="A {adjective} {subject} {action}",
            params={"adjective": ["majestic", "serene"], "subject": ["cat", "mountain"]},
        )
        pb.render(adjective="majestic", subject="cat")  # → "A majestic cat"
        pb.render_with_params()  # → 从 params 池随机选值
    """

    name: str
    template: str
    params: dict[str, list[str]] = field(default_factory=dict)
    weight: float = 1.0

    def render(self, **kwargs) -> str:
        """填充指定参数渲染出文本。"""
        return self.template.format(**kwargs)

    def render_with_params(self, **overrides) -> str:
        """从 params 池中随机选择参数（支持 override）。"""
        selected = {}
        for key, values in self.params.items():
            if key in overrides:
                selected[key] = overrides[key]
            else:
                selected[key] = random.choice(values)
        return self.template.format(**selected)

    def __str__(self) -> str:
        return f"PromptBlock({self.name}, weight={self.weight})"


@dataclass
class PromptTemplate:
    """完整的 prompt 模板 = 多个 PromptBlock 按顺序组合。

    Example:
        template = PromptTemplate(
            name="portrait",
            blocks=[subject_block, lighting_block],
            separator=", ",
        )
        template.render(subject="woman", light_type="soft", creative_level=5)
    """

    name: str
    blocks: list[PromptBlock] = field(default_factory=list)
    separator: str = ", "
    style_categories: list[StyleCategory] = field(default_factory=list)

    def render(self, **kwargs) -> str:
        """渲染所有 block 并用 separator 连接。

        支持 creative_level 参数控制复杂度：
        - level 1-3: 全部 blocks 渲染
        - level 4-7: 全部 blocks + params 池随机值
        - level 8-10: 全部 blocks + 多样化 params
        """
        creative_level = kwargs.pop("creative_level", 5)

        parts = []
        for block in self.blocks:
            if block.params and creative_level >= 4:
                # 中高创意：从 params 池随机选
                rendered = block.render_with_params(**kwargs)
            elif block.params:
                # 低创意：用第一个参数值
                first_params = {k: v[0] for k, v in block.params.items()}
                combined = {**first_params, **kwargs}
                rendered = block.render(**combined)
            else:
                # 无参数池：用传进来的 kwargs
                rendered = block.render(**kwargs)
            parts.append(rendered)

        # 高创意等级可加额外修饰
        result = self.separator.join(parts)
        if creative_level >= 8:
            quality_modifiers = [
                "highly detailed", "professional quality",
                "masterpiece", "award-winning composition",
            ]
            result += f", {random.choice(quality_modifiers)}"

        return result

    def add_block(self, block: PromptBlock) -> "PromptTemplate":
        """追加一个 block。"""
        self.blocks.append(block)
        return self
