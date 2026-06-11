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


class OptimizeRequest(BaseModel):
    """优化请求"""
    prompt: str = Field(..., min_length=1, max_length=2000, description="原始提示词")
    platform: PlatformType = Field(default=PlatformType.GENERIC, description="目标平台")
    style: Optional[StyleType] = Field(default=None, description="艺术风格")
    creative_level: int = Field(default=5, ge=1, le=10, description="创意程度 1-10")
    max_length: int = Field(default=500, ge=50, le=2000, description="优化结果最大字符数")
    negative_prompt: Optional[str] = Field(default=None, max_length=500, description="负面提示词，避免的元素")


class OptimizeResult(BaseModel):
    """优化结果"""
    optimized_prompt: str = Field(..., description="优化后的提示词")
    platform: PlatformType = Field(..., description="实际使用的平台策略")
    style: Optional[StyleType] = Field(default=None, description="使用的风格")
    model_used: str = Field(default="", description="LLM 模型名称")
    tokens_used: int = Field(default=0, description="消耗的 token 数")
    duration_ms: float = Field(default=0.0, description="优化耗时（毫秒）")
    error: Optional[str] = Field(default=None, description="出错时的错误信息")
