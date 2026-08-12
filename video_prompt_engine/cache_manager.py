"""双级缓存（内存 + SQLite 持久）——复刻图片引擎机制，独立实现。"""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path


class VideoCacheManager:
    def __init__(self, persist_dir: str | Path, memory_size: int = 512):
        self._lock = threading.Lock()
        self._mem: dict[str, dict] = {}
        self._mem_size = max(16, int(memory_size))
        persist = Path(persist_dir)
        persist.mkdir(parents=True, exist_ok=True)
        self._db_path = persist / "video_prompt_cache.db"
        self._init_db()

    def _init_db(self):
        with self._lock:
            conn = sqlite3.connect(str(self._db_path), timeout=5.0)
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("CREATE TABLE IF NOT EXISTS cache (cache_key TEXT PRIMARY KEY, result TEXT, created_at TEXT DEFAULT (datetime('now')))")
            conn.commit()
            conn.close()

    def _conn(self):
        conn = sqlite3.connect(str(self._db_path), timeout=5.0)
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def get(self, cache_key: str) -> dict | None:
        with self._lock:
            if cache_key in self._mem:
                return self._mem[cache_key]
        try:
            conn = self._conn()
            row = conn.execute("SELECT result FROM cache WHERE cache_key = ?", (cache_key,)).fetchone()
            conn.close()
            if row:
                data = json.loads(row[0])
                with self._lock:
                    self._mem[cache_key] = data
                return data
        except Exception:
            pass
        return None

    def stats(self) -> dict:
        """缓存统计：内存条数/容量 + SQLite 持久条数。"""
        mem = len(self._mem)
        db_count = 0
        try:
            conn = self._conn()
            row = conn.execute("SELECT COUNT(*) FROM cache").fetchone()
            conn.close()
            db_count = row[0] if row else 0
        except Exception:
            db_count = 0
        return {"memory_size": mem, "memory_capacity": self._mem_size, "sqlite_count": db_count}

    def set(self, cache_key: str, result: dict):
        with self._lock:
            self._mem[cache_key] = result
            if len(self._mem) > self._mem_size:
                # 简单淘汰：清空重建（低频操作）
                self._mem = dict(list(self._mem.items())[-self._mem_size:])
        try:
            conn = self._conn()
            conn.execute(
                "INSERT OR REPLACE INTO cache (cache_key, result) VALUES (?, ?)",
                (cache_key, json.dumps(result, ensure_ascii=False)),
            )
            # 持久层容量裁剪：超过 memory_size*4 时按最旧淘汰（防止 DB 无限增长）
            try:
                conn.execute(
                    "DELETE FROM cache WHERE cache_key IN ("
                    " SELECT cache_key FROM cache ORDER BY created_at DESC LIMIT -1 OFFSET ?)",
                    (self._mem_size * 4,),
                )
            except Exception:
                pass
            conn.commit()
            conn.close()
        except Exception:
            pass
