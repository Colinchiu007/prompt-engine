"""数据模型 — Pydantic 类型定义"""
from typing import Optional
from enum import Enum
from pydantic import BaseModel, Field


class PlatformType(str, Enum):
    """支持的图片生成平台"""
    MIDJOURNEY = "midjourney"
    STABLE_DIFFUSION = "stable_diffusion"
    DALLE = "dalle"
    TONGYI = "tongyi"        # 通义万相
    YIZHANG = "yizhang"      # 文心一格
    JIMENG = "jimeng"        # 即梦
    GENERIC = "generic"      # 通用


class StyleType(str, Enum):
    """支持的艺术风格"""
    REALISTIC = "realistic"      # 写实
    CARTOON = "cartoon"          # 卡通
    ANIME = "anime"              # 动漫
    OIL_PAINTING = "oil_painting" # 油画
    WATERCOLOR = "watercolor"    # 水彩
    PIXEL = "pixel"              # 像素
    CYBERPUNK = "cyberpunk"      # 赛博朋克
    FANTASY = "fantasy"          # 奇幻
    PHOTOGRAPHY = "photography"  # 摄影
    _3D_RENDER = "3d_render"     # 3D 渲染
    MINIMALIST = "minimalist"    # 极简
    ABSTRACT = "abstract"        # 抽象
    PORTRAIT = "portrait"        # 人像
    LANDSCAPE = "landscape"      # 风景


# ============================================================================
# MJ Style Reference Categories
# ============================================================================

class StyleCategory(str, Enum):
    """MJ 风格分类器维度 — 26 个风格分类

    来源: github.com/willwulfken/MidJourney-Styles-and-Keywords-Reference
    覆盖: 光照/材质/色彩/镜头/构图/自然/艺术媒介/文化风格/影视参考/特效
    """
    # 视觉风格
    DESIGN_STYLES = "design_styles"          # 设计风格
    DIGITAL = "digital"                       # 数字艺术
    EXPERIMENTAL = "experimental"             # 实验风格

    # 光影与材质
    LIGHTING = "lighting"                    # 光照效果
    MATERIAL_PROPERTIES = "material_properties"  # 材质属性
    MATERIALS = "materials"                  # 材料
    DIMENSIONALITY = "dimensionality"        # 维度感

    # 色彩
    COLORS_AND_PALETTES = "colors_and_palettes"  # 色彩与调色板
    COMBINATIONS = "combinations"                 # 色彩组合

    # 相机与镜头
    CAMERA = "camera"                         # 相机/镜头
    PERSPECTIVE = "perspective"               # 视角/透视
    STRUCTURAL_MODIFICATION = "structural_modification"  # 结构变形

    # 自然与生物
    NATURE_AND_ANIMALS = "nature_and_animals"  # 自然与动物
    OBJECTS = "objects"                       # 物体
    OUTER_SPACE = "outer_space"               # 太空

    # 几何与形态
    GEOMETRY = "geometry"                     # 几何形状

    # 文化
    GEOGRAPHY_AND_CULTURE = "geography_and_culture"  # 地理与文化

    # 艺术媒介
    DRAWING_AND_ART_MEDIUMS = "drawing_and_art_mediums"  # 绘画与艺术媒介

    # 特效
    SFX_AND_SHADERS = "sfx_and_shaders"      # 特效与着色器

    # 主题
    THEMES = "themes"                          # 主题/氛围
    INTANGIBLES = "intangibles"                # 抽象概念

    # 影视音乐
    TV_AND_MOVIES = "tv_and_movies"            # 影视参考
    SONG_LYRICS = "song_lyrics"                # 歌词风格

    # 杂项
    EMOJIS = "emojis"                          # Emoji 风格
    MISCELLANEOUS = "miscellaneous"            # 杂项


class StyleCategoryResult(BaseModel):
    """分类结果 — 多标签输出（一个 prompt 可能触发多个风格维度）"""
    categories: list[StyleCategory] = Field(
        default_factory=list,
        description="检测到的风格类别列表"
    )
    keywords_found: dict[str, list[str]] = Field(
        default_factory=dict,
        description="每个类别中匹配的原始关键词"
    )
    method: str = Field(
        default="keyword_match",
        description="分类方法: keyword_match / llm_classify / vector_rag"
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="总体置信度"
    )


class AutoStyleRequest(BaseModel):
    """自动风格识别请求"""
    prompt: str = Field(..., min_length=1, max_length=2000, description="待分析的原始 prompt")
    platform: PlatformType = Field(default=PlatformType.GENERIC, description="目标平台")
    use_llm: bool = Field(default=True, description="是否使用 LLM 做深度分类")
    max_categories: int = Field(default=5, ge=1, le=10, description="最多返回几个风格类别")


class OptimizeRequest(BaseModel):
    """优化请求"""
    prompt: str = Field(..., min_length=1, max_length=2000, description="原始提示词")
    platform: PlatformType = Field(default=PlatformType.GENERIC, description="目标平台")
    style: Optional[StyleType] = Field(default=None, description="艺术风格")
    creative_level: int = Field(default=5, ge=1, le=10, description="创意程度 1-10")
    max_length: int = Field(default=300, ge=50, le=2000, description="优化结果最大字符数")
    user_tier: int = Field(default=0, ge=0, le=3, description="用户会员等级 0=未指定 1=免费 2=标准 3=专业")
    user_own_key: Optional[str] = Field(default=None, description="用户自带的 API Key（优先级最高）")
    negative_prompt: Optional[str] = Field(default=None, max_length=500, description="负面提示词，避免的元素")
    num_candidates: int = Field(default=1, ge=1, le=5, description="候选版本数量，用于 A/B 测试")
    auto_detect_style: bool = Field(
        default=True,
        description="如果 style=None 且此项为 True，自动从 prompt 检测风格类别"
    )
    context: Optional[dict] = Field(default=None, description="PROJECT-012 注入的上下文：synopsis, character, setting, character_list。用于角色一致性")


class BatchOptimizeRequest(BaseModel):
    """批量优化请求"""
    requests: list[OptimizeRequest] = Field(..., min_length=1, max_length=10, description="优化请求列表，最多 10 条")


class ReverseRequest(BaseModel):
    """图片逆向工程请求"""
    image_url: str = Field(..., description="图片 URL")
    platform: PlatformType = Field(default=PlatformType.GENERIC, description="目标平台")
    style: Optional[StyleType] = Field(default=None, description="艺术风格")
    detail: str = Field(default="auto", description="视觉分析详细度: low / auto / high")


class ReverseResult(BaseModel):
    """逆向工程结果"""
    prompt: str = Field(..., description="生成的提示词")
    platform: PlatformType = Field(..., description="目标平台")
    style: Optional[StyleType] = Field(default=None, description="艺术风格")
    model_used: str = Field(default="", description="LLM 模型名称")
    description: str = Field(default="", description="图片描述（纯文本版本）")
    duration_ms: float = Field(default=0.0, description="耗时")
    error: Optional[str] = Field(default=None, description="错误信息")


class OptimizeResult(BaseModel):
    """优化结果"""
    optimized_prompt: str = Field(..., description="优化后的提示词")
    platform: PlatformType = Field(..., description="实际使用的平台策略")
    style: Optional[StyleType] = Field(default=None, description="使用的风格")
    model_used: str = Field(default="", description="LLM 模型名称")
    tokens_used: int = Field(default=0, description="消耗的 token 数")
    duration_ms: float = Field(default=0.0, description="优化耗时（毫秒）")
    candidates: list[str] = Field(default_factory=list, description="多候选版本（A/B 测试时返回）")
    key_source: str = Field(default="config", description="Key 来源: user/official/config")
    error: Optional[str] = Field(default=None, description="出错时的错误信息")
    detected_categories: Optional[StyleCategoryResult] = Field(
        default=None,
        description="自动检测到的 MJ 风格类别（当 auto_detect_style=True 时填充）"
    )


class RewriteRequest(BaseModel):
    """Prompt 扩写请求（灵感: Infinity 项目）"""
    prompt: str = Field(..., min_length=1, max_length=500, description="原始简短描述")
    platform: PlatformType = Field(default=PlatformType.GENERIC, description="目标平台")
    max_length: int = Field(default=500, ge=50, le=2000, description="输出最大字符数")


class FeedbackEntry(BaseModel):
    """风格分类反馈记录."""
    id: str = Field(default="", description="反馈 ID（自动生成）")
    prompt: str = Field(..., description="被分类的 prompt")
    detected_categories: list[str] = Field(default_factory=list, description="分类器检测到的类别")
    corrected_categories: list[str] = Field(default_factory=list, description="用户纠正的类别")
    rating: int = Field(default=0, ge=0, le=5, description="用户评分 0-5 (0=未评分, 5=完全正确)")
    method: str = Field(default="", description="分类方法 (keyword_match/vector_rag/llm_classify)")
    confidence: float = Field(default=0.0, description="分类置信度")
    timestamp: str = Field(default="", description="反馈时间 ISO 格式")
    notes: str = Field(default="", description="用户备注")


class FeedbackStats(BaseModel):
    """反馈统计汇总."""
    total: int = Field(default=0, description="总反馈数")
    rated: int = Field(default=0, description="有评分的反馈数")
    avg_rating: float = Field(default=0.0, description="平均评分")
    corrected: int = Field(default=0, description="有纠正的反馈数")
    method_breakdown: dict[str, int] = Field(default_factory=dict, description="按分类方法的分布")


# ── 共享映射表（StyleCategory ↔ 各种表示形式）───
# 单一定义点，消除 optimizer.py / classifier.py / rest.py 三份重复

STYLE_CATEGORY_DB_MAP: dict["StyleCategory", str] = {
    StyleCategory.LIGHTING: "Lighting",
    StyleCategory.MATERIAL_PROPERTIES: "Material_Properties",
    StyleCategory.MATERIALS: "Materials",
    StyleCategory.DIMENSIONALITY: "Dimensionality",
    StyleCategory.COLORS_AND_PALETTES: "Colors_and_Palettes",
    StyleCategory.COMBINATIONS: "Combinations",
    StyleCategory.CAMERA: "Camera",
    StyleCategory.PERSPECTIVE: "Perspective",
    StyleCategory.STRUCTURAL_MODIFICATION: "Structural_Modification",
    StyleCategory.NATURE_AND_ANIMALS: "Nature_and_Animals",
    StyleCategory.OBJECTS: "Objects",
    StyleCategory.OUTER_SPACE: "Outer_Space",
    StyleCategory.GEOMETRY: "Geometry",
    StyleCategory.GEOGRAPHY_AND_CULTURE: "Geography_and_Culture",
    StyleCategory.DRAWING_AND_ART_MEDIUMS: "Drawing_and_Art_Mediums",
    StyleCategory.SFX_AND_SHADERS: "SFX_and_Shaders",
    StyleCategory.THEMES: "Themes",
    StyleCategory.INTANGIBLES: "Intangibles",
    StyleCategory.TV_AND_MOVIES: "TV_and_Movies",
    StyleCategory.SONG_LYRICS: "Song_Lyrics",
    StyleCategory.DESIGN_STYLES: "Design_Styles",
    StyleCategory.DIGITAL: "Digital",
    StyleCategory.EXPERIMENTAL: "Experimental",
    StyleCategory.EMOJIS: "Emojis",
    StyleCategory.MISCELLANEOUS: "Miscellaneous",
}

DB_KEY_TO_STYLE_CATEGORY: dict[str, "StyleCategory"] = {v: k for k, v in STYLE_CATEGORY_DB_MAP.items()}

CATEGORY_CN_NAMES: dict["StyleCategory", str] = {
    StyleCategory.LIGHTING: "光照效果",
    StyleCategory.MATERIAL_PROPERTIES: "材质属性",
    StyleCategory.MATERIALS: "材料",
    StyleCategory.DIMENSIONALITY: "维度感",
    StyleCategory.COLORS_AND_PALETTES: "色彩与调色板",
    StyleCategory.COMBINATIONS: "色彩组合",
    StyleCategory.CAMERA: "相机/镜头",
    StyleCategory.PERSPECTIVE: "视角/透视",
    StyleCategory.STRUCTURAL_MODIFICATION: "结构变形",
    StyleCategory.NATURE_AND_ANIMALS: "自然与动物",
    StyleCategory.OBJECTS: "物体",
    StyleCategory.OUTER_SPACE: "太空",
    StyleCategory.GEOMETRY: "几何形状",
    StyleCategory.GEOGRAPHY_AND_CULTURE: "地理与文化",
    StyleCategory.DRAWING_AND_ART_MEDIUMS: "绘画与艺术媒介",
    StyleCategory.SFX_AND_SHADERS: "特效与着色器",
    StyleCategory.THEMES: "主题/氛围",
    StyleCategory.INTANGIBLES: "抽象概念",
    StyleCategory.TV_AND_MOVIES: "影视参考",
    StyleCategory.SONG_LYRICS: "歌词风格",
    StyleCategory.DESIGN_STYLES: "设计风格",
    StyleCategory.DIGITAL: "数字艺术",
    StyleCategory.EXPERIMENTAL: "实验风格",
    StyleCategory.EMOJIS: "Emoji 风格",
    StyleCategory.MISCELLANEOUS: "杂项",
}

CATEGORY_DESCRIPTIONS: dict["StyleCategory", str] = {
    StyleCategory.LIGHTING: "光照效果、光线类型、照明方式、阴影、辉光、体积光",
    StyleCategory.MATERIAL_PROPERTIES: "材质属性、表面质感、透明度、反射、折射、光泽度",
    StyleCategory.MATERIALS: "建筑材料、物体材质、塑料、金属、织物、木材、石材",
    StyleCategory.DIMENSIONALITY: "维度表现、2D/3D/2.5D、立体感、空间深度",
    StyleCategory.COLORS_AND_PALETTES: "色彩方案、色调、调色板、互补色、类似色",
    StyleCategory.COMBINATIONS: "色彩组合、特殊色彩效果、发光材质、珍珠色",
    StyleCategory.CAMERA: "相机类型、镜头、摄影技法、光圈、焦距、拍摄手法",
    StyleCategory.PERSPECTIVE: "透视角度、视角、构图方式、仰视、俯视、鱼眼",
    StyleCategory.STRUCTURAL_MODIFICATION: "结构变形、螺旋、几何扭曲、抽象形态",
    StyleCategory.NATURE_AND_ANIMALS: "自然景观、动物、植物、生态系统、野外",
    StyleCategory.OBJECTS: "具体物体、道具、日常物品、机械、电子元件",
    StyleCategory.OUTER_SPACE: "太空、星空、星球、宇宙、星际、银河",
    StyleCategory.GEOMETRY: "几何图形、图案、多面体、对称、伊斯兰几何",
    StyleCategory.GEOGRAPHY_AND_CULTURE: "文化风格、地域特色、民族、历史时期、建筑传统",
    StyleCategory.DRAWING_AND_ART_MEDIUMS: "绘画媒介、艺术技法、水彩、油画、素描、版画",
    StyleCategory.SFX_AND_SHADERS: "视觉特效、着色器效果、光效、粒子、后期处理",
    StyleCategory.THEMES: "主题氛围、情绪、概念、美学运动、亚文化",
    StyleCategory.INTANGIBLES: "抽象概念、不可见的、量子、能量、光、电磁",
    StyleCategory.TV_AND_MOVIES: "影视参考、电影风格、电视剧、动画、漫画",
    StyleCategory.SONG_LYRICS: "歌词风格、音乐相关、歌词意象、旋律视觉化",
    StyleCategory.DESIGN_STYLES: "设计风格、艺术运动、装饰艺术、极简、波普",
    StyleCategory.DIGITAL: "数字艺术、像素艺术、电子游戏风格、CGI",
    StyleCategory.EXPERIMENTAL: "实验风格、前卫、概念艺术、非常规",
    StyleCategory.EMOJIS: "Emoji 风格、表情符号、Unicode 符号",
    StyleCategory.MISCELLANEOUS: "杂项、其他、特殊渲染效果",
}
