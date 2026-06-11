"""Stable Diffusion 平台策略"""
from prompt_engine.strategies.base import BaseStrategy, register
from prompt_engine.models import PlatformType, StyleType


@register("stable_diffusion")
class StableDiffusionStrategy(BaseStrategy):
    """Stable Diffusion 提示词优化策略"""

    platform = PlatformType.STABLE_DIFFUSION

    @classmethod
    def build_system_prompt(
        cls,
        style: StyleType | None = None,
        creative_level: int = 5,
        max_length: int = 500,
    ) -> str:
        style_text = f"风格：{style.value}" if style else "不限定风格"
        return f"""你是一位 Stable Diffusion 提示词专家。你的任务是将用户输入的简单描述改写成高质量的 SD 提示词。

## 规则
1. 输出**只包含提示词本身**，不要解释、不要评价、不要额外的文字
2. 使用英文输出（即使输入是中文），因为 SD 对英文提示词理解更好
3. 保留用户原始描述的核心语义
4. 使用 SD 的权重语法：(keyword:1.2), [keyword:0.8]
5. 按重要性排序：主体 → 细节 → 环境 → 光照 → 风格 → 质量词
6. 质量词用 (masterpiece:1.2), (best quality:1.2), (highres:1.1), (8k:1.1) 开头
7. 输出长度控制在 {max_length} 字符以内
8. {style_text}"""

    @classmethod
    def post_process(cls, raw_output: str) -> str:
        text = raw_output.strip().strip('"').strip("'")
        # 如果输出包含中文关键词，追加英文标签
        return text