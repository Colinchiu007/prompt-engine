"""视频知识库加载（种子 + 关键词词典）。"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


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


def load_seed_video_prompts(path: Path) -> list[VideoPromptEntry]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    entries = []
    for i, item in enumerate(raw):
        entries.append(VideoPromptEntry(
            id=item.get("id", f"vseed-{i:04d}"),
            title=item.get("title", ""),
            description=item.get("description", ""),
            prompt_text=item.get("prompt_text", item.get("prompt", "")),
            language=item.get("language", "en"),
            platform=item.get("platform", "generic_video"),
            style=item.get("style", ""),
            categories=item.get("categories", []),
            quality_score=item.get("quality_score", 5),
            source=item.get("source", ""),
        ))
    return entries


def load_keywords_video(path: Path) -> dict[str, list[dict]]:
    """加载视频关键词词典：{dimension: [{zh, en}, ...]}。"""
    return json.loads(path.read_text(encoding="utf-8"))
