"""反馈闭环 — 好/坏反馈沉淀入种子库（质量分调整）+ 失败模式采集（P1-3）。

失败模式闭环：坏评可携带 failure_patterns 标签（对齐 knowledge/failure_patterns.json
规则库的 pattern 键），累计写入 failure_stats.json（seed 同目录），形成
「规则库（知识）→ 反馈标签（采集）→ 统计（驱动 evaluator 权重）」闭环。
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path


class VideoFeedbackStore:
    def __init__(self, seed_path: str | Path, failure_stats_path: str | Path | None = None):
        self._path = Path(seed_path)
        self._stats_path = Path(failure_stats_path) if failure_stats_path is not None else self._path.with_name("failure_stats.json")
        self._lock = threading.Lock()

    def _load(self) -> list[dict]:
        if not self._path.exists():
            return []
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            return []

    def _save(self, seeds: list[dict]):
        # 原子写：临时文件 + 替换，避免并发/半写状态（Windows 语义与图片引擎一致）
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(json.dumps(seeds, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            os.replace(tmp, self._path)
        finally:
            if tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass

    def _load_stats(self) -> dict[str, dict]:
        if not self._stats_path.exists():
            return {}
        try:
            return json.loads(self._stats_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_stats(self, stats: dict[str, dict]):
        self._stats_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._stats_path.with_suffix(self._stats_path.suffix + ".tmp")
        tmp.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            os.replace(tmp, self._stats_path)
        finally:
            if tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass

    def submit(self, prompt_text: str, result_prompt: str, good: bool, source: str = "user-feedback",
               failure_patterns: list[str] | None = None) -> dict:
        """提交反馈。bad + failure_patterns → 种子降分 + 失败模式统计累计。"""
        prompt_text = str(prompt_text or "").strip()
        result_prompt = str(result_prompt or "").strip()
        if not prompt_text or not result_prompt:
            raise ValueError("prompt_text / result_prompt 不能为空")
        with self._lock:
            result = self._submit_locked(prompt_text, result_prompt, good, source)
            events: dict[str, int] = {}
            if not good and failure_patterns:
                events = self._record_failure_patterns(failure_patterns, prompt_text)
            result["failure_events"] = events
            return result

    def _submit_locked(self, prompt_text: str, result_prompt: str, good: bool, source: str) -> dict:
        seeds = self._load()
        # 好反馈：结果提示词入种子（质量分 9）；坏反馈：源提示词质量分降级
        if good:
            entry = {
                "id": f"fb-{int(time.time() * 1000)}-{len(seeds):04d}",
                "title": result_prompt[:60],
                "description": "用户好评反馈沉淀",
                "prompt_text": result_prompt,
                "language": "en",
                "platform": "generic_video",
                "style": "video",
                "categories": ["video", "user-feedback"],
                "quality_score": 9,
                "source": source,
            }
            seeds.append(entry)
        else:
            for s in seeds:
                if s.get("prompt_text", "")[:60] == prompt_text[:60]:
                    s["quality_score"] = max(1, int(s.get("quality_score", 5)) - 1)
        self._save(seeds)
        return {"status": "ok", "total": len(seeds)}

    def _record_failure_patterns(self, patterns: list[str], prompt_text: str) -> dict[str, int]:
        """失败模式累计（P1-3）：pattern → {count, last_seen, recent_prompt}。

        未知 pattern 宽容记录（规则库是知识层，采集不应丢数据），
        单条截断防滥用；统计文件与种子库同目录。
        """
        stats = self._load_stats()
        events: dict[str, int] = {}
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        for raw in list(patterns or [])[:10]:
            pat = str(raw).strip()[:50]
            if not pat:
                continue
            entry = stats.setdefault(pat, {"count": 0, "last_seen": "", "recent_prompt": ""})
            entry["count"] = int(entry.get("count", 0)) + 1
            entry["last_seen"] = now
            entry["recent_prompt"] = str(prompt_text)[:100]
            events[pat] = entry["count"]
        self._save_stats(stats)
        return events

    def failure_stats(self) -> dict[str, dict]:
        """读取失败模式统计（只读，不落盘）。"""
        with self._lock:
            return self._load_stats()
