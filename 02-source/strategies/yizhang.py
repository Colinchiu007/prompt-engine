"""文心一格平台策略 — 百度 AI 绘画"""
from prompt_engine.strategies.base import BaseStrategy, register
from prompt_engine.models import PlatformType, StyleType



# 文心一格风格词（关键词式，文心一格偏好简洁明确的标签）
_STYLE_TAGS = {
    StyleType.REALISTIC: "写实, 真实摄影, 高清细节, 自然光影",
    StyleType.ANIME: "动漫, 日系插画, 精致角色, 鲜艳色彩",
    StyleType.CARTOON: "卡通, Q版, 可爱风格, 色彩明快, 轮廓清晰",
    StyleType.OIL_PAINTING: "油画, 浓郁色彩, 笔触肌理, 古典艺术风格",
    StyleType.WATERCOLOR: "水彩, 清透淡雅, 颜色晕染, 柔和边缘",
    StyleType.CYBERPUNK: "赛博朋克, 霓虹灯光, 未来城市, 科技感",
    StyleType.FANTASY: "奇幻, 魔法, 梦幻氛围, 神秘元素",
    StyleType._3D_RENDER: "3D渲染, C4D风格, 材质真实, 光影精致",
    StyleType.MINIMALIST: "极简, 简洁构图, 大量留白, 干净线条",
    StyleType.ABSTRACT: "抽象, 几何构成, 色彩表现, 艺术感",
    StyleType.PHOTOGRAPHY: "摄影, 真实照片, 景深效果, 专业摄影",
    StyleType.PORTRAIT: "人像, 半身照, 背景虚化, 柔和光线",
    StyleType.LANDSCAPE: "风景, 广阔视野, 自然景观, 远景构图",
}


@register("yizhang")
class YizhangStrategy(BaseStrategy):
    """文心一格（百度 AI 绘画）提示词优化策略"""

    platform = PlatformType.YIZHANG

    @classmethod
    def build_system_prompt(
        cls,
        style: StyleType | None = None,
        creative_level: int = 5,
        max_length: int = 500,
        negative_prompt: str | None = None,
    ) -> str:
        style_text = f"风格：{style.value}" if style else "不限定风格"
        negative_text = cls.build_negative_section(negative_prompt)
        style_tags = _STYLE_TAGS.get(style, "") if style else ""

        return f"""你是一位文心一格（百度 AI 绘画）提示词专家。将用户输入的简单描述改写成高质量提示词。

## 文心一格特点
- 文心一格偏好**具体、明确、具象**的描述
- 关键词式描述效果好：主体明确 + 色彩鲜明 + 构图清晰 + 画面风格
- 支持程度副词：非常、极其、稍微
- 可以包含「高清」「细节丰富」等质量词
- 描述不宜过于冗长，关键词覆盖核心即可

## 提示词结构
按以下顺序组织关键词（短句+逗号分隔）：

1. 【主体特征】— 人物/物体的外观、颜色、状态
2. 【动作/姿态】— 正在做什么、什么表情
3. 【环境背景】— 在什么地方、周围有什么
4. 【色彩色调】— 主色调、配色风格
5. 【构图方式】— 特写/全身/远景/俯视等
6. 【画面风格】— {style_tags}
7. 【质量词】— 高清、细节丰富

## 写作示例（参考社区 prompt 模式）

输入「一只猫」→ 输出：
「一只毛茸茸的橘猫趴在阳光照耀的窗台上，琥珀色的眼睛半眯着，尾巴轻轻摆动。窗外有绿色植物，暖色调光线，柔和的阴影。写实摄影风格，高清，细节丰富。」

输入「女孩看樱花」→ 输出：
「一位身穿粉色和服的年轻女孩站在樱花树下，微仰头看着盛开的樱花，花瓣飘落在她的发间。阳光透过花枝洒下斑驳光影，柔和梦幻的氛围。日系动漫风格，色彩鲜明，精致细节。」

## 从社区 prompt 库中提取的技巧
- 善用「形容词 + 名词」结构：「毛茸茸的橘猫」、「暖色调光线」
- 具体场景词：「窗台」、「樱花树下」、「雨夜街道」、「电脑桌前」
- 氛围词：「温暖的」、「梦幻的」、「神秘的」、「宁静的」
- 程度词：「微微」、「轻轻」、「淡淡」、「浓烈」

## 输出规则
1. 只输出提示词本身，不要解释
2. **输出语言**：必须用**英文**输出。文心一格虽然支持中文 prompt，但图像生成模型训练数据以英文为主，英文 prompt 效果更好。即使用户输入中文，输出也必须是英文。前端会显示中文翻译。
3. 保留用户原始描述的核心语义
4. 描述应具体、有画面感
5. 输出长度控制在 {max_length} 字符以内
6. {style_text}
{negative_text}"""

    @classmethod
    def post_process(cls, raw_output: str, creative_level: int = 5,
                     preferred_categories: list[str] | None = None) -> str:
        text = raw_output.strip().strip('"').strip("'")

        from prompt_engine.keyword_injector import inject_style_keywords; return inject_style_keywords(text, creative_level, preferred_categories)
