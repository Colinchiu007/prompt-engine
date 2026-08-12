"""输入自动分类 — 题材 + 镜头意图检测（关键词，无外部依赖）。"""
from __future__ import annotations

GENRE_KEYWORDS = {
    "history": ["历史", "朝代", "战役", "古代", "将军", "汉", "唐", "宋", "三国", "战争", "战场", "出征"],
    "scifi": ["未来", "科幻", "赛博", "霓虹", "太空", "机器", "全息", "cyber"],
    "ad": ["广告", "产品", "开箱", "品牌", "电商", "宣传", "slogan"],
    "drama": ["短剧", "剧情", "分镜", "对白", "情感", "drama"],
    "nature": ["自然", "风景", "山川", "森林", "海洋", "动物", "natural"],
    "portrait": ["人物", "人像", "表情", "肖像", "portrait", "face"],
    "cinematic": ["电影", "大片", "史诗", "cinematic", "epic", "纪录"],
}
SHOT_INTENT = {
    "dynamic": ["奔跑", "追逐", "爆炸", "战斗", "飞行", "旋转", "疾驰", "dynamic", "chase", "explode"],
    "static": ["静", "静止", "凝视", "特写", "stationary", "still"],
    "wide": ["全景", "远景", "山川", "城市", "wide", "landscape", "establishing"],
    "closeup": ["特写", "面部", "细节", "close-up", "close up", "macro"],
}


def classify(prompt: str) -> dict:
    lower = str(prompt).lower()
    genres = [g for g, kws in GENRE_KEYWORDS.items() if any(k.lower() in lower or k in prompt for k in kws)]
    intents = [s for s, kws in SHOT_INTENT.items() if any(k.lower() in lower or k in prompt for k in kws)]
    return {
        "genres": genres[:3] or ["general"],
        "shot_intents": intents[:2],
        "primary_genre": (genres or ["general"])[0],
    }

# 题材 → 建议关键词维度（用于 system prompt 注入与关键词词典优先维度）
GENRE_DIM_MAP = {
    "history": ["scene", "style", "camera", "lighting"],
    "scifi": ["scene", "color", "material", "style", "lighting"],
    "ad": ["action", "color", "lighting", "scene"],
    "drama": ["action", "camera", "scene", "style"],
    "nature": ["scene", "lighting", "color", "camera"],
    "portrait": ["style", "lighting", "camera", "scene"],
    "cinematic": ["camera", "style", "scene", "lighting"],
    "general": [],
}


def suggest_dimensions(prompt: str) -> list[str]:
    """按输入题材建议关键词维度（去重保序；general 返回空）。"""
    info = classify(prompt)
    dims: list[str] = []
    for genre in info.get("genres") or []:
        for dim in GENRE_DIM_MAP.get(genre, []):
            if dim not in dims:
                dims.append(dim)
    return dims
