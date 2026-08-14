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
    def from_dict(cls, item: dict, fallback_prefix: str = "seed", idx: int = 0) -> "SeedEntry":
        return cls(
            id=item.get("id", f"{fallback_prefix}-{idx:04d}"),
            title=item.get("title", ""),
            description=item.get("description", ""),
            prompt_text=item.get("prompt_text", item.get("prompt", "")),
            language=item.get("language", "en"),
            platform=item.get("platform", "generic"),
            style=item.get("style", ""),
            categories=item.get("categories", []),
            quality_score=item.get("quality_score", 5),
            source=item.get("source", ""),
        )


def load_seed_entries(path: str | Path, fallback_prefix: str = "seed") -> list[SeedEntry]:
    """加载种子 JSON（兼容 prompt_text 或 prompt 字段）。"""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return [SeedEntry.from_dict(item, fallback_prefix=fallback_prefix, idx=i) for i, item in enumerate(raw)]


def load_keywords(path: str | Path) -> dict[str, list[dict]]:
    """加载关键词词典：{dimension: [{zh, en}, ...]}。"""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_index(seed_path: str | Path, persist_dir: str | Path, data_file: str = "index.json") -> int:
    """种子 → TF-IDF 索引（清空重建）。返回条目数。"""
    store = PromptVectorStore(persist_dir, data_file=data_file)
    entries = load_seed_entries(seed_path)
    # 与视频引擎 build.py 语义一致：clear + add_prompts（add 内部 save）
    store.clear()
    store.add_prompts(entries)
    return store.count
