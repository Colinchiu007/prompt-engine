"""MJ 风格关键词注入 — 跨平台共享模块

从 MidJourney Style Reference 数据库抽取风格关键词，
注入到各平台的优化后 prompt 中。
"""
import json
import random
import re
from pathlib import Path


# 全局缓存
_MJ_STYLE_DB: dict | None = None

# 创意等级 → 默认类别列表（回退用，覆盖 1-10 所有等级）
_DEFAULT_CATEGORIES_BY_LEVEL: dict[int, list[str]] = {
    1: ["Lighting", "Material_Properties"],
    2: ["Lighting", "Material_Properties"],
    3: ["Lighting", "Material_Properties"],
    4: ["Lighting", "Material_Properties", "Colors_and_Palettes"],
    5: ["Lighting", "Material_Properties", "Colors_and_Palettes", "Camera"],
    6: ["Lighting", "Material_Properties", "Colors_and_Palettes", "Camera"],
    7: ["Lighting", "Material_Properties", "Colors_and_Palettes", "Camera",
        "Design_Styles", "Nature_and_Animals", "Themes",
        "SFX_and_Shaders", "Perspective", "Drawing_and_Art_Mediums"],
    8: ["Lighting", "Material_Properties", "Colors_and_Palettes", "Camera",
        "Design_Styles", "Nature_and_Animals", "Themes",
        "SFX_and_Shaders", "Perspective", "Drawing_and_Art_Mediums"],
    9: ["Lighting", "Material_Properties", "Colors_and_Palettes", "Camera",
        "Design_Styles", "Nature_and_Animals", "Themes",
        "SFX_and_Shaders", "Perspective", "Drawing_and_Art_Mediums"],
    10: ["Lighting", "Material_Properties", "Colors_and_Palettes", "Camera",
         "Design_Styles", "Nature_and_Animals", "Themes",
         "SFX_and_Shaders", "Perspective", "Drawing_and_Art_Mediums"],
}

_NOISE_WORDS = {"LED", "LCD", "UV", "CRT", "CFL", "OLED", "AMOLED", "HDR", "RGB", "CMYK"}


def load_mj_style_db() -> dict | None:
    """加载 MJ 风格关键词数据库（懒加载，跨平台共享）。"""
    global _MJ_STYLE_DB
    if _MJ_STYLE_DB is not None:
        return _MJ_STYLE_DB
    db_path = Path(__file__).parent / "data" / "mj_style_final.json"
    if db_path.exists():
        try:
            with open(db_path, "r", encoding="utf-8") as f:
                _MJ_STYLE_DB = json.load(f)
            return _MJ_STYLE_DB
        except Exception:
            pass
    return None


def filter_noise_keywords(kws: list[str]) -> list[str]:
    """过滤 MJ 关键词中的噪音词。"""
    good = []
    for k in kws:
        upper = k.upper()
        if any(nw in upper for nw in _NOISE_WORDS):
            continue
        if all(c.isdigit() for c in k):
            continue
        if len(k) >= 4 or " " in k or "-" in k or "\u00a0" in k:
            good.append(k)
    return good


def inject_style_keywords(
    prompt: str,
    creative_level: int = 5,
    preferred_categories: list[str] | None = None,
) -> str:
    """从 MJ 风格数据库注入风格关键词到 prompt。

    如果提供了 preferred_categories（检测到的风格类别），优先从中选择关键词。
    否则按创意等级随机选类别。
    跨平台通用，MJ、SD、DALL-E 等均可使用。

    Args:
        prompt: 格式化后的 prompt 文本
        creative_level: 创意等级 1-10
        preferred_categories: MJ 数据库 key 列表（如 ["Lighting", "Camera"]）

    Returns:
        注入关键词后的 prompt
    """
    db = load_mj_style_db()
    if not db:
        return prompt

    # 确定注入数量
    if creative_level <= 2:
        num = 0  # 低创意不注入
    elif creative_level <= 3:
        num = random.randint(0, 1)
    elif creative_level <= 6:
        num = random.randint(1, 3)
    else:
        num = random.randint(2, 5)

    if num == 0:
        return prompt

    # 确定类别来源
    if preferred_categories:
        available = [c for c in preferred_categories if c in db]
        if not available:
            available = _DEFAULT_CATEGORIES_BY_LEVEL.get(creative_level, ["Lighting"])
        cats_for_injection = random.sample(available, min(num, len(available)))
    else:
        cats_for_injection = random.sample(
            _DEFAULT_CATEGORIES_BY_LEVEL.get(creative_level, ["Lighting"]),
            min(num, 10),
        )

    inject_kws = []
    for cat in cats_for_injection:
        kws = db.get(cat, [])
        good = filter_noise_keywords(kws)
        if good:
            inject_kws.append(random.choice(good))

    if inject_kws:
        injected = ", " + ", ".join(inject_kws)
        return prompt.rstrip(",. ") + injected + "."

    return prompt