"""文心一格平台策略"""
from prompt_engine.strategies.base import BaseStrategy, register
from prompt_engine.models import PlatformType, StyleType


@register("yizhang")
class YizhangStrategy(BaseStrategy):
    """百度文心一格提示词优化策略"""

    platform = PlatformType.YIZHANG

    @classmethod
    def build_system_prompt(
        cls,
        style: StyleType | None = None,
        creative_level: int = 5,
        max_length: int = 500,
    ) -> str:
        style_text = f"风格：{style.value}" if style else "不限定风格"
        return f"""你是一位文心一格（百度 AI 绘画）提示词专家。你的任务是将用户输入的简单描述改写成高质量的中文提示词。

## 规则
1. 输出**只包含提示词本身**，不要解释、不要评价、不要额外的文字
2. 使用中文输出
3. 保留用户原始描述的核心语义
4. 文心一格偏好具象化描述：主体明确、色彩鲜明、构图清晰
5. 包含：主体特征、色彩色调、构图方式、画面风格
6. 输出长度控制在 {max_length} 字符以内
7. {style_text}"""