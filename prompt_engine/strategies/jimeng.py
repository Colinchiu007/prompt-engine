"""即梦平台策略 — 字节跳动 AI 绘画"""
from prompt_engine.strategies.base import BaseStrategy, register
from prompt_engine.models import PlatformType, StyleType


# 即梦视觉风格描述
_STYLE_VISION = {
    StyleType.REALISTIC:
        "写实风格，超真实质感，光影对比强烈，细节锐利。",
    StyleType.ANIME:
        "动漫风格，线条流畅，色彩饱和，角色灵动，充满动感。",
    StyleType.CARTOON:
        "卡通风格，色彩鲜艳明快，造型圆润可爱，视觉冲击力强。",
    StyleType.OIL_PAINTING:
        "油画风格，笔触粗犷有力，色彩浓郁饱满，极具质感。",
    StyleType.WATERCOLOR:
        "水彩风格，色彩通透，画面轻盈，边缘柔和水润。",
    StyleType.CYBERPUNK:
        "赛博朋克，霓虹光影交错，夜雨都市，强对比色彩，科技感爆棚。",
    StyleType.FANTASY:
        "奇幻史诗风格，宏大的场景，炫目的魔法光效，神秘氛围。",
    StyleType._3D_RENDER:
        "3D渲染，材质表现力强，光影精确，画面通透有质感。",
    StyleType.MINIMALIST:
        "极简设计，大面积的纯色背景，干净利落的线条，视觉焦点突出。",
    StyleType.ABSTRACT:
        "抽象艺术，流动的色彩，不规则的形态，强烈的视觉张力。",
    StyleType.PHOTOGRAPHY:
        "摄影写实，高动态范围，画面层次丰富，沉浸感强。",
    StyleType.PORTRAIT:
        "人像摄影，肤质细腻，眼神有光，背景简洁突出人物。",
    StyleType.LANDSCAPE:
        "风光大片，恢宏视野，光线层次丰富，色彩饱和通透。",
}


@register("jimeng")
class JimengStrategy(BaseStrategy):
    """即梦（字节跳动 AI 绘画）提示词优化策略 — 强视觉冲击力"""

    platform = PlatformType.JIMENG

    @classmethod
    def _impact_words(cls, creative_level: int) -> str:
        """根据创意度生成冲击力描述"""
        if creative_level <= 3:
            return "简洁清晰，视觉舒适"
        elif creative_level <= 5:
            return "视觉冲击力强，色彩鲜明，层次丰富"
        elif creative_level <= 7:
            return "强烈视觉冲击，极致光影对比，色彩饱和度高，画面张力十足"
        else:
            return "极具视觉震撼力，光影戏剧化，色彩浓烈张扬，画面富有叙事感和情绪张力"

    @classmethod
    def build_system_prompt(
        cls,
        style: StyleType | None = None,
        creative_level: int = 5,
        max_length: int = 500,
    ) -> str:
        style_text = f"风格：{style.value}" if style else "不限定风格"
        style_vision = _STYLE_VISION.get(style, "") if style else ""
        impact = cls._impact_words(creative_level)

        return f"""你是一位即梦（字节跳动 AI 绘画）提示词专家。将用户输入的简单描述改写成高质量提示词。

## 即梦特点（字节跳动旗下 AI 绘画平台）
- 突出**视觉冲击力**，强光影对比、鲜艳色彩、动态构图
- 画面感强，描述要有"能看见"的质感
- 支持多种画幅：横版/竖版/方版，在描述中自然带出
- 支持风格强度控制，可以用程度词调节

## 提示词结构

写一段富有画面感、视觉张力强的中文描述，按此顺序：

1. 【主体】—「一个/一位...」开头，精确描述主体特征
   - 不加修饰的直白描述 + 修饰词点缀
   - 例：「一位身穿红色风衣的短发女性站在雨夜的霓虹灯下」

2. 【动态/瞬间】— 抓住最有张力的瞬间
   - 即梦擅长动态画面：动作正在进行中、光线正在变化
   - 例：「她回眸的一瞬间，风衣下摆被风吹起，雨滴在灯光下闪闪发光」

3. 【光影】— 这是即梦的核心优势
   - 描述光源位置、光线质量、阴影形状、光晕效果
   - 例：「左侧暖色霓虹灯光打在脸上，右侧冷色月光勾勒轮廓，形成强烈对比」

4. 【色彩】— 鲜明、饱和、有对比
   - 点名主色调和点缀色
   - 例：「主色调是深蓝和品红，霓虹灯带出紫色和青色的点缀」

5. 【构图】— 有张力的构图
   - 近景特写、低角度仰视、对角线构图、框架式构图
   - 例：「低角度仰拍，人物占据画面三分之二，霓虹招牌作为背景框架」

6. 【质量词】— 高清、细节丰富、质感
   - {impact}

## 风格指导
{style_vision}

## 从社区 prompt 中提取的技巧
- 动词选"有力量"的：投下、划过、扑面而来、穿透、弥漫、闪耀
- 色彩用"有冲击力"的词：烈焰红、霓虹紫、暗夜蓝、金属银
- 光影用"有对比"的词：逆光、轮廓光、剪影、强对比、光晕
- 构图用"有张力"的词：低角度、仰视、框架构图、对角线、前中后景

## 输出规则
1. 只输出提示词本身，不要解释
2. 使用中文输出
3. 保留用户原始描述的核心语义
4. 写成一到两个短段落，有画面冲击力
5. 输出长度控制在 {max_length} 字符以内
6. {style_text}"""

    @classmethod
    def post_process(cls, raw_output: str) -> str:
        return raw_output.strip().strip('"').strip("'")