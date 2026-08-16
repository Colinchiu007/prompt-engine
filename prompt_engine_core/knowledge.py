"""知识库骨架 — 跨引擎共享的种子加载/构建机械件。

来源：视频引擎 knowledge/loader.py + build.py，提炼为通用骨架。
两引擎各自的种子文件（seed_video_prompts.json / seed_prompts.json）保留在领域层，
core 只提供参数化的加载与索引构建。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from prompt_engine_core.vector_store import PromptVectorStore


@dataclass
class SeedEntry:
    id: str
    title: str
    description: str
    prompt_text: str
    language: str = "en"
    platform: str = "generic"
    style: str = ""
    categories: list[str] = field(default_factory=list)
    quality_score: int = 5
    source: str = ""

    @classmethod
    def from_dict(
        cls, item: dict, fallback_prefix: str = "seed", idx: int = 0, default_platform: str = "generic",
    ) -> "SeedEntry":
        return cls(
            id=item.get("id", f"{fallback_prefix}-{idx:04d}"),
            title=item.get("title", ""),
            description=item.get("description", ""),
            prompt_text=item.get("prompt_text", item.get("prompt", "")),
            language=item.get("language", "en"),
            platform=item.get("platform", default_platform),
            style=item.get("style", ""),
            categories=item.get("categories", []),
            quality_score=item.get("quality_score", 5),
            source=item.get("source", ""),
        )


def load_seed_entries(
    path: str | Path, fallback_prefix: str = "seed", default_platform: str = "generic",
) -> list[SeedEntry]:
    """加载种子 JSON（兼容 prompt_text 或 prompt 字段）。

    default_platform 仅作为「字段缺失」时的回退值；显式写入的 platform 原样保留。
    """
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return [
        SeedEntry.from_dict(
            item, fallback_prefix=fallback_prefix, idx=i, default_platform=default_platform,
        )
        for i, item in enumerate(raw)
    ]


def load_keywords(path: str | Path) -> dict[str, list[dict]]:
    """加载关键词词典：{dimension: [{zh, en}, ...]}。"""
    return json.loads(Path(path).read_text(encoding="utf-8"))


_ELEMENT_KEYWORDS_CACHE: dict | None = None

# 回退默认（与 element_keywords.json 资产逐词一致，构建期由 tests/test_evaluator_p0p2.py 一致性用例保证不漂移；资产缺失/损坏时零回归）
_ELEMENT_KEYWORDS_FALLBACK: dict =     {
      "subject": {
        "en": [
          "character",
          "subject",
          "hero",
          "heroic",
          "woman",
          "man",
          "general",
          "people",
          "person",
          "warrior",
          "soldier",
          "horse",
          "cat",
          "dog",
          "robot",
          "mech",
          "machine",
          "police",
          "crowd",
          "girl",
          "boy",
          "child",
          "knight",
          "assassin",
          "pilot"
        ],
        "zh": [
          "人",
          "将军",
          "女子",
          "士兵",
          "战士",
          "主角",
          "机器人",
          "警察",
          "人群",
          "女孩",
          "男孩",
          "儿童",
          "机器",
          "人物",
          "男人",
          "女人",
          "男子",
          "少年",
          "青年",
          "老人",
        ],
        "ru": [
          "персонаж",
          "герой",
          "человек",
          "солдат",
          "воин",
          "робот",
          "девушка",
          "мальчик",
          "ребёнок",
          "толпа",
          "полицейский",
          "полицейских",
          "мужчина",
          "мужчины",
          "женщина",
          "женщины",
          "группа"
        ]
      },
      "action": {
        "en": [
          "running",
          "walking",
          "riding",
          "fighting",
          "motion",
          "moving",
          "move",
          "runs",
          "rushing",
          "chasing",
          "flying",
          "dancing",
          "walk",
          "posing",
          "standing",
          "sitting",
          "staring",
          "strike",
          "charging",
          "explode",
          "explosion",
          "blast",
          "aiming"
        ],
        "zh": [
          "飞翔",
          "飞行",
          "飞奔",
          "奔跑",
          "战斗",
          "作战",
          "行走",
          "走出",
          "走近",
          "走进",
          "跑步",
          "追逐",
          "追赶",
          "追捕",
          "追上",
          "舞蹈",
          "跳舞",
          "骑马",
          "站立",
          "站起",
          "坐下",
          "凝视",
          "注视",
          "遥望",
          "眺望",
          "手持",
          "挥舞",
          "挥动",
          "攻击",
          "进攻",
          "飞溅",
          "飞过",
        ],
        "ru": [
          "бежит",
          "бег",
          "движение",
          "идёт",
          "летит",
          "бой",
          "сражается",
          "стоит",
          "сидит",
          "взрыв"
        ]
      },
      "environment": {
        "en": [
          "environment",
          "scene",
          "background",
          "landscape",
          "city",
          "street",
          "room",
          "interior",
          "exterior",
          "forest",
          "desert",
          "mountain",
          "sea",
          "ocean",
          "snow",
          "wasteland",
          "ruins",
          "station",
          "warehouse"
        ],
        "zh": [
          "原野",
          "街道",
          "室内",
          "森林",
          "沙漠",
          "雪地",
          "废墟",
          "基地",
          "车站",
          "室外",
          "城市",
          "城堡",
          "背景",
          "前景",
          "场景",
          "景色",
          "景观",
          "夜景",
        ],
        "ru": [
          "город",
          "улица",
          "комната",
          "лес",
          "пустыня",
          "горы",
          "море",
          "снег",
          "развалины",
          "станция",
          "фон",
          "фоне"
        ]
      },
      "lighting": {
        "en": [
          "light",
          "lighting",
          "sunlight",
          "golden hour",
          "glow",
          "backlight",
          "rim light",
          "moonlight",
          "neon",
          "flare",
          "haze",
          "gloom",
          "dark",
          "bright",
          "beam"
        ],
        "zh": [
          "光线",
          "光源",
          "灯光",
          "阳光",
          "月光",
          "日光",
          "烛光",
          "火光",
          "主光",
          "暖光",
          "冷光",
          "白光",
          "红光",
          "蓝光",
          "绿光",
          "荧光",
          "微光",
          "亮光",
          "发光",
          "闪光",
          "辉光",
          "逆光",
          "霓虹",
          "光晕",
          "光束",
        ],
        "ru": [
          "свет",
          "освещение",
          "неон",
          "блик",
          "лунный",
          "закат",
          "тень",
          "свечение"
        ]
      },
      "color": {
        "en": [
          "color",
          "palette",
          "hue",
          "red",
          "blue",
          "green",
          "gold",
          "golden",
          "black",
          "white",
          "dark",
          "monochrome",
          "sepia",
          "teal",
          "orange",
          "purple",
          "gray",
          "grey"
        ],
        "zh": [
          "黑白",
          "色彩",
          "色调",
          "颜色",
          "配色",
          "色温",
          "灰色",
          "灰白",
          "银灰",
          "红色",
          "绯红",
          "鲜红",
          "暗红",
          "血红",
          "橙红",
          "蓝色",
          "湛蓝",
          "深蓝",
          "淡蓝",
          "蔚蓝",
          "绿色",
          "翠绿",
          "深绿",
          "橄榄绿",
          "金色",
          "金黄",
          "铂金",
          "黑色",
          "漆黑",
          "墨黑",
          "乌黑",
          "白色",
          "纯白",
          "雪白",
          "苍白",
        ],
        "ru": [
          "цвет",
          "красный",
          "синий",
          "зелёный",
          "золотой",
          "чёрный",
          "белый",
          "палитра",
          "серый",
          "серой",
          "сером",
          "однотонный",
          "однотонном"
        ]
      },
      "style": {
        "en": [
          "style",
          "cinematic",
          "epic",
          "cinematography",
          "documentary",
          "moody",
          "hazy",
          "blur",
          "blurred",
          "grain",
          "grainy",
          "vignette",
          "contrast",
          "noir",
          "cyberpunk",
          "sci-fi",
          "fantasy",
          "realistic",
          "photoreal",
          "aesthetic"
        ],
        "zh": [
          "风格",
          "写实",
          "纪实",
          "动漫",
          "赛博",
          "风格化",
        ],
        "ru": [
          "стиль",
          "кинематографичный",
          "реалистичный",
          "нуар",
          "нео-нуар",
          "эстетика",
          "документальный"
        ]
      }
    }



def load_element_keywords(path: str | Path | None = None) -> tuple[dict, bool]:
    """加载六要素关键词资产 {element: {lang: [words]}}（视频/图片评估器共享）。

    返回 (keywords, from_asset)。资产缺失/损坏/结构非法 → 回退内置默认（from_asset=False），
    保证任何环境下评估器行为可用；结果模块级缓存。
    """
    global _ELEMENT_KEYWORDS_CACHE
    if path is None and _ELEMENT_KEYWORDS_CACHE is not None:
        return _ELEMENT_KEYWORDS_CACHE, True
    target = Path(path) if path is not None else Path(__file__).resolve().parent / "knowledge" / "element_keywords.json"
    try:
        if target.exists():
            data = json.loads(target.read_text(encoding="utf-8"))
            elements = data.get("elements") or {}
            _REQUIRED_ELEMENTS = ("subject", "action", "environment", "lighting", "color", "style")
            if all(
                isinstance(elements.get(k), dict)
                and {"en", "zh", "ru"} <= set(elements[k])
                and all(isinstance(elements[k][lang], list) and elements[k][lang] for lang in ("en", "zh", "ru"))
                for k in _REQUIRED_ELEMENTS
            ):
                if path is None:
                    _ELEMENT_KEYWORDS_CACHE = elements
                return elements, True
    except Exception:
        pass
    if path is None:
        _ELEMENT_KEYWORDS_CACHE = _ELEMENT_KEYWORDS_FALLBACK
    return _ELEMENT_KEYWORDS_FALLBACK, False


def build_index(seed_path: str | Path, persist_dir: str | Path, data_file: str = "index.json") -> int:
    """种子 → TF-IDF 索引（清空重建）。返回条目数。"""
    store = PromptVectorStore(persist_dir, data_file=data_file)
    entries = load_seed_entries(seed_path)
    # 与视频引擎 build.py 语义一致：clear + add_prompts（add 内部 save）
    store.clear()
    store.add_prompts(entries)
    return store.count
