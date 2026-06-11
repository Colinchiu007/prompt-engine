"""通用平台策略（不限定平台）"""
from prompt_engine.strategies.base import BaseStrategy, register
from prompt_engine.models import PlatformType, StyleType


@register("generic")
class GenericStrategy(BaseStrategy):
    """通用提示词优化策略"""

    platform = PlatformType.GENERIC

    @classmethod
    def build_system_prompt(
        cls,
        style: StyleType | None = None,
        creative_level: int = 5,
        max_length: int = 500,
    ) -> str:
        style_text = f"风格：{style.value}" if style else "不限定风格"
        return f"""你是一位 AI 绘画提示词专家。你的任务是将用户输入的简单描述改写成高质量的通用提示词。

## 规则
1. 输出**只包含提示词本身**，不要解释、不要评价、不要额外的文字
2. 保留用户原始描述的核心语义，不要偏离
3. 添加细节：主体描述、环境、光照、材质、视角、色彩、氛围
4. 根据创意程度（{creative_level}/10）决定添加细节的多少
5. 输出长度控制在 {max_length} 字符以内
6. 输出语言与用户输入保持一致
7. {style_text}"""