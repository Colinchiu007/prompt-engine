"""原子写与进程内锁 — 跨引擎共享的文件持久化机械件。

来源：视频引擎 feedback.py（tmp + os.replace + threading.Lock），提炼为通用工具。
图片引擎 feedback 的直写 _save 迁移到此工具后获得同等原子性。
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Callable


def atomic_write_text(path: str | Path, content: str, encoding: str = "utf-8") -> None:
    """原子写文本：临时文件 + os.replace，避免并发/半写状态。

    Windows 语义：os.replace 是原子替换；临时文件在 finally 中清理。
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(content, encoding=encoding)
    try:
        os.replace(tmp, target)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def atomic_write_json(path: str | Path, data: Any, ensure_ascii: bool = False, indent: int = 2) -> None:
    """原子写 JSON（ensure_ascii=False 保留中文可读性）。"""
    atomic_write_text(path, json.dumps(data, ensure_ascii=ensure_ascii, indent=indent), encoding="utf-8")


class FileLockedStore:
    """带进程内锁的 JSON 文件存储基类。

    子类只需实现 _transform(entries) -> new_entries（读改写语义），
    提交在锁内完成：load → transform → atomic save。
    """

    def __init__(self, path: str | Path):
        self._path = Path(path)
        self._lock = threading.Lock()

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> list[dict]:
        if not self._path.exists():
            return []
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def mutate(self, fn: Callable[[list[dict]], list[dict]]) -> list[dict]:
        """锁内 load → fn → 原子 save，返回新列表。"""
        with self._lock:
            entries = self.load()
            entries = fn(entries) or []
            atomic_write_json(self._path, entries)
            return entries
