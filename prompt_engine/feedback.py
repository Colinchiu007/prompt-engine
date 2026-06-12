"""反馈存储 — 记录风格分类的用户反馈，持久化到 JSON 文件"""
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from prompt_engine.models import FeedbackEntry, FeedbackStats


class FeedbackStore:
    """反馈存储：追加写到 JSON 文件，无外部依赖。"""

    def __init__(self, persist_path: str = "./feedback_db.json"):
        self._path = Path(persist_path)
        self._entries: list[FeedbackEntry] = []
        self._load()

    def _data_path(self) -> Path:
        return self._path

    def _load(self):
        if self._path.exists():
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._entries = [FeedbackEntry(**e) for e in data]
            except Exception:
                self._entries = []

    def _save(self):
        data = [e.model_dump() for e in self._entries]
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def submit(self, entry: FeedbackEntry) -> FeedbackEntry:
        """提交一条反馈。自动生成 ID 和时间戳。"""
        if not entry.id:
            entry.id = str(uuid.uuid4())[:8]
        if not entry.timestamp:
            entry.timestamp = datetime.now(timezone.utc).isoformat()
        self._entries.append(entry)
        self._save()
        return entry

    def stats(self) -> FeedbackStats:
        """计算反馈统计。"""
        total = len(self._entries)
        if total == 0:
            return FeedbackStats()

        rated = [e for e in self._entries if e.rating > 0]
        corrected = [e for e in self._entries if e.corrected_categories]
        method_breakdown: dict[str, int] = {}
        for e in self._entries:
            if e.method:
                method_breakdown[e.method] = method_breakdown.get(e.method, 0) + 1

        avg_rating = sum(e.rating for e in rated) / len(rated) if rated else 0.0

        return FeedbackStats(
            total=total,
            rated=len(rated),
            avg_rating=round(avg_rating, 2),
            corrected=len(corrected),
            method_breakdown=method_breakdown,
        )

    def recent(self, limit: int = 10) -> list[FeedbackEntry]:
        """最近 N 条反馈。"""
        return list(reversed(self._entries[-limit:]))

    @property
    def count(self) -> int:
        return len(self._entries)


# 全局单例
_feedback_store: Optional[FeedbackStore] = None


def get_feedback_store(persist_path: str = "./feedback_db.json") -> FeedbackStore:
    global _feedback_store
    if _feedback_store is None:
        _feedback_store = FeedbackStore(persist_path)
    return _feedback_store
