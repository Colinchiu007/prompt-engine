"""Style detection — keyword matching + MJ category inference.

Extracted from optimizer.py God Class refactoring (Phase 1).
"""

import logging
from typing import Optional, TYPE_CHECKING

from prompt_engine.models import StyleType, StyleCategory

if TYPE_CHECKING:
    from prompt_engine.models import StyleCategoryResult

logger = logging.getLogger(__name__)

# ── 反向映射：关键词 → StyleType
_STYLE_TYPE_KEYWORDS: dict[StyleType, list[str]] = {
    # 具体媒介排前面（更高优先级）
    StyleType.WATERCOLOR: ["watercolor", "water colour", "water-colour",
                           "水彩", "水彩画"],
    StyleType.OIL_PAINTING: ["oil painting", "oil paint",
                             "油画"],
    StyleType.PIXEL: ["pixel art", "8-bit", "retro game", "pixel",
                      "像素", "像素画", "点阵"],
    StyleType.ANIME: ["anime", "manga", "cel shaded", "cell shade", "japanese animation",
                      "动漫", "动画", "二次元"],
    StyleType.CARTOON: ["cartoon", "comic", "toon",
                        "卡通", "漫画风格", "美式卡通"],
    # 设计风格
    StyleType.CYBERPUNK: ["cyberpunk", "neon", "dystopian", "cyber",
                          "赛博朋克", "赛博", "霓虹"],
    StyleType.MINIMALIST: ["minimalist", "minimal", "clean", "simple",
                           "极简", "简约", "极简主义"],
    StyleType.FANTASY: ["fantasy", "magical", "mythical", "medieval", "dragon", "elf",
                        "奇幻", "魔法", "神话"],
    StyleType.ABSTRACT: ["abstract", "abstract art",
                         "抽象", "抽象画"],
    # 摄影与写实
    StyleType.PHOTOGRAPHY: ["photography", "photo", "camera", "lens", "photograph", "portrait", "shot on",
                            "摄影", "相机", "镜头", "照片"],
    StyleType.PORTRAIT: ["portrait", "headshot", "close-up", "face",
                         "人像", "肖像", "特写"],
    StyleType.REALISTIC: ["realistic", "photorealistic", "realism", "hyperrealistic",
                          "写实", "逼真"],
    # 技术类
    StyleType._3D_RENDER: ["3d render", "cgi", "pbr", "render", "3d model", "vray",
                           "3D渲染", "渲染", "三维"],
    StyleType.LANDSCAPE: ["landscape", "mountain", "sea", "ocean", "nature", "scenery", "vista",
                          "风景", "山水", "自然", "景观", "风光"],
}


def detect_style_type_from_category(
    category_result: "StyleCategoryResult",
    prompt: str,
) -> tuple[Optional[StyleType], Optional["StyleCategoryResult"]]:
    """从 MJ 风格分类结果自动推断 StyleType。

    1. 优先匹配 StyleType 关键词
    2. 如果没匹配到，回退到 StyleCategory → StyleType 映射
    """
    prompt_lower = prompt.lower()

    # 第一轮：关键词匹配 StyleType
    for st, keywords in _STYLE_TYPE_KEYWORDS.items():
        for kw in keywords:
            if kw in prompt_lower:
                return st, category_result

    # 第二轮：StyleCategory 映射
    if category_result and category_result.categories:
        # 媒体类别直接映射
        if StyleCategory.DRAWING_AND_ART_MEDIUMS in category_result.categories:
            if any(kw in prompt_lower for kw in ["watercolor", "water colour", "水彩"]):
                return StyleType.WATERCOLOR, category_result
            if any(kw in prompt_lower for kw in ["oil painting", "oil paint", "油画"]):
                return StyleType.OIL_PAINTING, category_result
            if any(kw in prompt_lower for kw in ["pixel art", "pixel", "像素"]):
                return StyleType.PIXEL, category_result

        if StyleCategory.DIGITAL in category_result.categories:
            if any(kw in prompt_lower for kw in ["pixel", "retro game", "8-bit"]):
                return StyleType.PIXEL, category_result
            return StyleType._3D_RENDER, category_result

        if StyleCategory.CAMERA in category_result.categories:
            return StyleType.PHOTOGRAPHY, category_result

        if StyleCategory.NATURE_AND_ANIMALS in category_result.categories:
            if any(kw in prompt_lower for kw in ["portrait", "close-up", "face", "人像", "肖像"]):
                return StyleType.PORTRAIT, category_result
            return StyleType.LANDSCAPE, category_result

    return None, category_result


def style_category_to_db_key(cat: StyleCategory) -> str:
    """将 StyleCategory 枚举值转换为 MJ 数据库的 key（硬编码映射，保证 100% 准确）。"""
    from prompt_engine.models import STYLE_CATEGORY_DB_MAP
    return STYLE_CATEGORY_DB_MAP.get(cat, cat.value.replace("_", " ").title().replace(" ", "_"))


def get_preferred_db_keys(category_result: Optional["StyleCategoryResult"]) -> list[str]:
    """从分类结果中提取 MJ DB 可用的 key 列表。"""
    if not category_result or not category_result.categories:
        return []
    return [style_category_to_db_key(cat) for cat in category_result.categories]
