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
    max_length: int = Field(default=500, ge=50, le=2000, description="优化结果最大字符数")
    negative_prompt: Optional[str] = Field(default=None, max_length=500, description="负面提示词，避免的元素")
    num_candidates: int = Field(default=1, ge=1, le=5, description="候选版本数量，用于 A/B 测试")
    auto_detect_style: bool = Field(
        default=True,
        description="如果 style=None 且此项为 True，自动从 prompt 检测风格类别"
    )


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
