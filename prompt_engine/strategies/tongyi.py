"""通义万相平台策略"""
from prompt_engine.strategies.base import BaseStrategy, register
from prompt_engine.models import PlatformType, StyleType


@register("tongyi")
class TongyiStrategy(BaseStrategy):
    """通义万相（阿里）提示词优化策略"""

    platform = PlatformType.TONGYI

    @classmethod
    def build_system_prompt(
        cls,
        style: StyleType | None = None,
        creative_level: int = 5,
        max_length: int = 500,
    ) -> str:
        style_text = f"风格：{style.value}" if style else "不限定风格"
        return f"""你是一位通义万相（阿里云 AI 绘画）提示词专家。你的任务是将用户输入的简单描述改写成高质量的中文提示词。

## 规则
1. 输出**只包含提示词本身**，不要解释、不要评价、不要额外的文字
2. 使用中文输出
3. 保留用户原始描述的核心语义
4. 使用通义万相的优化风格：简洁但富有画面感的中文描述
5. 包含：主体、动作/状态、环境、光线、氛围
6. 输出长度控制在 {max_length} 字符以内
7. {style_text}"""