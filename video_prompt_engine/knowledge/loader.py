"""视频知识库加载（种子 + 关键词词典）。"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from prompt_engine_core.knowledge import load_keywords, load_seed_entries


@dataclass
class VideoPromptEntry:
    id: str
    title: str
    description: str
    prompt_text: str
    language: str = "en"
    platform: str = "generic_video"
    style: str = ""
    categories: list[str] = field(default_factory=list)
    quality_score: int = 5
    source: str = ""


def _seed_to_entry(e) -> VideoPromptEntry:
    return VideoPromptEntry(
        id=e.id, title=e.title, description=e.description, prompt_text=e.prompt_text,
        language=e.language, platform=e.platform, style=e.style,
        categories=list(e.categories), quality_score=e.quality_score, source=e.source,
    )


@lru_cache(maxsize=4)
def _load_seed_entries_cached(path: str, extra_path: str | None) -> tuple[VideoPromptEntry, ...]:
    """缓存版种子加载（主文件 + 可选 higgsfield 语料文件合并）。

    语料文件 ~3MB（去重后 258 条），多个 VideoOptimizer 实例共享一次解析结果；
    extra_path 缺失时静默跳过（旧 checkout 兼容）。
    """
    entries = [_seed_to_entry(e) for e in load_seed_entries(path, fallback_prefix="vseed", default_platform="generic_video")]
    if extra_path:
        extra = Path(extra_path)
        if extra.exists():
            entries += [_seed_to_entry(e) for e in load_seed_entries(extra, fallback_prefix="hg", default_platform="generic_video")]
    return tuple(entries)


def load_seed_video_prompts(path: Path, extra_path: Path | None = None) -> list[VideoPromptEntry]:
    """加载视频种子（复用共享内核解析骨架，保持 VideoPromptEntry 领域模型）。

    平台字段缺失时回退 generic_video（历史行为）；显式写入的 platform 原样保留。
    extra_path（如 seed_higgsfield_prompts.json）存在时合并加载（P2.9 语料资产化）。
    """
    return list(_load_seed_entries_cached(str(path), str(extra_path) if extra_path is not None else None))


def load_keywords_video(path: Path) -> dict[str, list[dict]]:
    """加载视频关键词词典：{dimension: [{zh, en}, ...]}（复用共享内核骨架）。"""
    return load_keywords(path)


def load_director_styles(path: Path) -> list[dict]:
    """加载导演/摄影指导风格词典：[{name_en, name_zh, aliases, style_desc, look}]。"""
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_director_style(style_text: str, styles: list[dict]) -> dict | None:
    """在 style 文本中匹配导演/摄影指导名（别名大小写不敏感子串），返回命中的风格条目。

    命中优先级按词典顺序（首条命中）；未命中返回 None（普通风格文本不受影响）。
    """
    if not style_text:
        return None
    low = style_text.lower()
    for entry in styles:
        names = [entry["name_en"], entry["name_zh"]] + entry.get("aliases", [])
        if any(n and n.lower() in low for n in names):
            return entry
    return None

def load_failure_patterns(path: Path) -> list[dict]:
    """加载失败模式规则库：[{pattern, name, category, check, severity, tags, evidence}]。

    P1-3 失败模式闭环：FAIL CHECK 判据 + 语料禁令聚类沉淀为可机器化规则，
    供 evaluator 扩展扣分项与反馈采集标签映射。
    """
    return json.loads(path.read_text(encoding="utf-8"))

def load_character_descriptors(path: Path) -> list[dict]:
    """加载角色描述符资产库（P1-4 Assets 卡模式）：[{
        id, name, name_zh, aliases, descriptor, views, negative, variants, evidence
    }]。"""
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_character_descriptor(name_text: str, cards: list[dict]) -> dict | None:
    """在角色名文本中匹配资产库卡片（英文/中文名 + 别名，大小写不敏感子串）。

    命中返回卡片；未命中返回 None（自定义角色不受影响）。
    """
    if not name_text:
        return None
    low = name_text.lower()
    for card in cards:
        names = [card["name"], card["name_zh"]] + card.get("aliases", [])
        if any(n and n.lower() in low for n in names):
            return card
    return None
