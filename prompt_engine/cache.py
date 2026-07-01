"""SQLite 持久化缓存 + L1 内存缓存

分层缓存设计：
  L1: MemoryPromptCache（热点数据，FIFO 淘汰）
  L2: SqlitePromptCache（持久化，TTL 过期）

降级：SQLite 不可用时自动回退到纯内存缓存。
"""
import hashlib
import logging
import os
import sqlite3
import time
from pathlib import Path
from typing import Optional

from prompt_engine.models import OptimizeResult

logger = logging.getLogger(__name__)

# 默认数据库路径
_DEFAULT_DB_PATH = Path(__file__).parent / "data" / "prompt_cache.db"


class SqlitePromptCache:
    """SQLite 持久化缓存（L2），重启不丢失。

    Schema:
        prompt_cache (
            cache_key TEXT PRIMARY KEY,       -- sha256(prompt|platform|creative_level|...)
            prompt TEXT NOT NULL,
            platform TEXT NOT NULL,
            creative_level INTEGER,
            max_length INTEGER,
            negative_prompt TEXT DEFAULT '',
            num_candidates INTEGER DEFAULT 1,
            result_json TEXT NOT NULL,         -- OptimizeResult.model_dump_json()
            created_at REAL NOT NULL,          -- time.time()
            hit_count INTEGER DEFAULT 1
        )
    """

    def __init__(self, db_path: Optional[str] = None, ttl_hours: int = 48):
        self._db_path = db_path or str(_DEFAULT_DB_PATH)
        self._ttl_hours = ttl_hours
        self._write_count = 0
        self._conn: Optional[sqlite3.Connection] = None
        self._init()

    def _init(self):
        """初始化数据库连接和表结构"""
        try:
            db_dir = os.path.dirname(self._db_path)
            if db_dir and not os.path.exists(db_dir):
                os.makedirs(db_dir, exist_ok=True)

            self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS prompt_cache (
                    cache_key TEXT PRIMARY KEY,
                    prompt TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    creative_level INTEGER,
                    max_length INTEGER,
                    negative_prompt TEXT DEFAULT '',
                    num_candidates INTEGER DEFAULT 1,
                    result_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    hit_count INTEGER DEFAULT 1
                )
            """)
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_cache_created ON prompt_cache(created_at)")
            self._conn.commit()

            # 启动时 vacuum 过期条目
            self.vacuum()
            logger.info("SqlitePromptCache ready: %s (ttl=%dh)", self._db_path, self._ttl_hours)
        except Exception as e:
            logger.warning("SqlitePromptCache init failed (%s), falling back to memory-only", e)
            self._conn = None

    def _check_ready(self) -> bool:
        return self._conn is not None

    @staticmethod
    def make_key(prompt: str, platform: str, creative_level: int,
                 max_length: int, negative_prompt: str, num_candidates: int) -> str:
        """生成缓存键"""
        raw = f"{prompt}|{platform}|{creative_level}|{max_length}|{negative_prompt}|{num_candidates}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get(self, prompt: str, platform: str, creative_level: int,
            max_length: int, negative_prompt: str, num_candidates: int) -> Optional[OptimizeResult]:
        """读取缓存，命中时返回结果（tokens=0, duration_ms=0），未命中返回 None"""
        if not self._check_ready():
            return None

        key = self.make_key(prompt, platform, creative_level, max_length, negative_prompt, num_candidates)
        cutoff = time.time() - self._ttl_hours * 3600

        try:
            row = self._conn.execute(
                "SELECT result_json FROM prompt_cache WHERE cache_key = ? AND created_at > ?",
                (key, cutoff)
            ).fetchone()

            if row:
                # 更新命中次数
                self._conn.execute(
                    "UPDATE prompt_cache SET hit_count = hit_count + 1 WHERE cache_key = ?",
                    (key,)
                )
                self._conn.commit()

                result = OptimizeResult.model_validate_json(row["result_json"])
                # 缓存命中时重置指标
                result.tokens_used = 0
                result.duration_ms = 0
                return result

            return None
        except Exception as e:
            logger.warning("SqlitePromptCache.get failed: %s", e)
            return None

    def set(self, prompt: str, platform: str, creative_level: int,
            max_length: int, negative_prompt: str, num_candidates: int,
            result: OptimizeResult):
        """写入缓存"""
        if not self._check_ready():
            return

        key = self.make_key(prompt, platform, creative_level, max_length, negative_prompt, num_candidates)

        try:
            self._conn.execute("""
                INSERT OR REPLACE INTO prompt_cache
                    (cache_key, prompt, platform, creative_level, max_length,
                     negative_prompt, num_candidates, result_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                key, prompt, platform, creative_level, max_length,
                negative_prompt, num_candidates,
                result.model_dump_json(), time.time()
            ))
            self._conn.commit()

            self._write_count += 1
            if self._write_count % 100 == 0:
                self.vacuum()
        except Exception as e:
            logger.warning("SqlitePromptCache.set failed: %s", e)

    def vacuum(self):
        """清理过期条目并回收空间"""
        if not self._check_ready():
            return
        try:
            cutoff = time.time() - self._ttl_hours * 3600
            deleted = self._conn.execute(
                "DELETE FROM prompt_cache WHERE created_at < ?", (cutoff,)
            ).rowcount
            if deleted:
                self._conn.execute("VACUUM")
                self._conn.commit()
                logger.info("SqlitePromptCache vacuum: deleted %d expired entries", deleted)
        except Exception as e:
            logger.warning("SqlitePromptCache.vacuum failed: %s", e)

    def stats(self) -> dict:
        """缓存统计"""
        if not self._check_ready():
            return {"entries": 0, "total_hits": 0, "storage": "sqlite(offline)", "ttl_hours": self._ttl_hours}

        try:
            total = self._conn.execute("SELECT COUNT(*) FROM prompt_cache").fetchone()[0]
            hit_total = self._conn.execute(
                "SELECT COALESCE(SUM(hit_count), 0) FROM prompt_cache"
            ).fetchone()[0]
            oldest = self._conn.execute(
                "SELECT MIN(created_at) FROM prompt_cache"
            ).fetchone()[0]
            return {
                "entries": total,
                "total_hits": hit_total,
                "oldest_entry": oldest,
                "ttl_hours": self._ttl_hours,
                "storage": "sqlite",
            }
        except Exception as e:
            logger.warning("SqlitePromptCache.stats failed: %s", e)
            return {"entries": 0, "total_hits": 0, "storage": "sqlite(error)", "ttl_hours": self._ttl_hours}

    def close(self):
        """关闭数据库连接"""
        if self._conn:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    def __del__(self):
        self.close()


class MemoryPromptCache:
    """L1 内存缓存（加速热点数据，FIFO 淘汰）"""

    def __init__(self, max_entries: int = 1000):
        self._cache: dict[str, OptimizeResult] = {}
        self._max = max_entries

    def get(self, key: str) -> Optional[OptimizeResult]:
        return self._cache.get(key)

    def set(self, key: str, result: OptimizeResult):
        if len(self._cache) >= self._max:
            # FIFO 淘汰
            self._cache.pop(next(iter(self._cache)))
        self._cache[key] = result

    def clear(self):
        self._cache.clear()

    @property
    def size(self) -> int:
        return len(self._cache)
