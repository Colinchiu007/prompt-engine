"""通义万相平台策略 — 阿里云 AI 绘画"""
from prompt_engine.strategies.base import BaseStrategy, register
from prompt_engine.models import PlatformType, StyleType



# 通义万相支持的中文风格描述
_STYLE_DESC = {
    StyleType.REALISTIC:
        "写实摄影风格。注重真实感，光影自然，细节清晰，材质真实。",
    StyleType.ANIME:
        "动漫插画风格。线条干净，色彩鲜明，角色造型精致，日系动画质感。",
    StyleType.CARTOON:
        "卡通风格。轮廓清晰，色彩明快，造型夸张可爱，轻松活泼氛围。",
    StyleType.OIL_PAINTING:
        "油画风格。可见笔触，色彩浓郁，画面有厚重感和肌理质感。",
    StyleType.WATERCOLOR:
        "水彩风格。颜色自然晕染，边缘柔和，纸张纹理可见，清透淡雅。",
    StyleType.CYBERPUNK:
        "赛博朋克风格。霓虹灯光（青/紫/粉），雨夜街道，高科技低生活氛围。",
    StyleType.FANTASY:
        "奇幻风格。魔法光芒，神秘氛围，宏大场景，幻想生物和元素。",
    StyleType._3D_RENDER:
        "3D 渲染风格。材质真实，光影精确，模型精致，PBR 材质质感。",
    StyleType.MINIMALIST:
        "极简风格。简洁线条，大量留白，色彩克制（单色或有限色），干净构图。",
    StyleType.ABSTRACT:
        "抽象艺术风格。几何或流动形态，色彩组合富有表现力，非具象表达。",
    StyleType.PHOTOGRAPHY:
        "摄影风格。真实照片感，精确曝光，自然景深，专业摄影质感。",
    StyleType.PORTRAIT:
        "人像摄影风格。突出人物，背景虚化，光线柔和，皮肤质感自然。",
    StyleType.LANDSCAPE:
        "风景景观风格。宏大开阔的视野，丰富的自然细节，沉浸感强。",
}


@register("tongyi")
class TongyiStrategy(BaseStrategy):
    """通义万相（阿里云 AI 绘画）提示词优化策略"""

    platform = PlatformType.TONGYI

    @classmethod
    def _detail_level(cls, creative_level: int) -> str:
        maps = {
            1: "只需要最简短的描述：主体和基本动作。",
            2: "适当增加少量细节描述。",
            3: "描述主体、环境、整体氛围。",
            4: "描述主体细节、环境、光线方向、色彩倾向。",
            5: "主体描述 + 环境 + 光线 + 色彩 + 构图。",
            6: "详细：主体特征、服饰、表情、环境、光线、色彩、材质。",
            7: "丰富描述：主体的精确特征、服装材质、多层次环境、光线设置、配色方案。",
            8: "非常详细：主体精细特征、环境细节、光照方向和质量、色彩搭配、构图技巧。",
            9: "极其详细：主体全面刻画、服装面料和纹样、多区域场景、复杂光线、配色主题。",
            10: "最大细节：主体全维度描述、前景/中景/背景分层、主光/辅光/轮廓光、精确配色、多种材质对比、构图法则。",
        }
        return maps.get(creative_level, maps[5])

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
        style_desc = _STYLE_DESC.get(style, "") if style else ""
        detail = cls._detail_level(creative_level)

        return f"""你是一位通义万相（阿里云 AI 绘画）提示词专家。将用户输入的简单描述改写成高质量中文提示词。

## 通义万相语法规则
- 使用**中文自然语言**描述，不需要特殊参数或符号
- 通义万相对中文理解好，建议使用中文输出
- 描述应简洁但富有画面感，避免生硬的标签式堆砌
- 可指定比例（竖图/方图/横图），在描述结尾自然带出

## 提示词结构（参考 10,000+ 社区图片生成提示词模式）
按以下顺序构建一段流畅的中文描述：

1. 【主体】— 精确描述：外貌特征、服装、姿态、表情
   「一位 25 岁左右的东亚女性，身材纤细，浅棕色长发及腰，身穿浅蓝色针织开衫...」

2. 【动作】— 具体动词，描述正在做什么
   「她微微侧身站立，右手举着手机在面前，左手自然下垂...」

3. 【环境】— 详细的场景设置
   「画面是从墙面镜中看到的卧室电脑角。白色书桌上有一台显示器，显示蓝色壁纸...」

4. 【色彩】— 主色调和点缀色
   「整体色调为蓝色系：浅蓝、天蓝、灰蓝色，营造出冷静统一的气氛。」

5. 【光线】— 光源、质量、方向
   「柔和的漫射日光从左侧大窗户透过纱帘照入，投下浅浅的阴影。」

6. 【风格/氛围】— 艺术风格、情感氛围
   {style_desc}

## 细节程度（创意度 {creative_level}/10）
{detail}

## 从社区 prompt 中提取的写作技巧
- 用精确的颜色描述：「藏蓝色」、「薄荷绿」、「柠檬黄」、「暖琥珀色」
- 描述表情细节：「眼神专注，表情认真，嘴角带着淡淡的微笑」
- 标注材质：「蓬松的针织面料」、「光滑的陶瓷表面」、「哑光金属质感」
- 描述光线：「柔和的漫射自然光」、「戏剧性侧光」、「逆光边缘光」
- 多用具象词：「格子花纹」、「蕾丝边」、「珍珠耳环」、「机械键盘」
- 多元素场景时，交代每个元素的位置：「左侧...中央...背景处...」

## 输出规则
1. 只输出提示词本身，不要解释、不要额外文字
2. 保留用户原始描述的核心语义，不要偏离
3. **输出语言**：必须用**英文**输出。通义万相虽然中文理解好，但图像生成模型训练数据以英文为主，英文 prompt 质量更高。即使用户输入中文，输出也必须是英文。前端会显示中文翻译。
4. 写成一个流畅的段落，自然语言风格
5. 输出长度控制在 {max_length} 字符以内
6. {style_text}
{negative_text}"""

    @classmethod
    def post_process(cls, raw_output: str, creative_level: int = 5,
                     preferred_categories: list[str] | None = None) -> str:
        text = raw_output.strip().strip('"').strip("'")

        from prompt_engine.keyword_injector import inject_style_keywords; return inject_style_keywords(text, creative_level, preferred_categories).strip("“").strip("”")
