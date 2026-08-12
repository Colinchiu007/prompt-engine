"""反馈闭环 — 好/坏反馈沉淀入种子库（质量分调整）。"""
from __future__ import annotations

import json
from pathlib import Path


class VideoFeedbackStore:
    def __init__(self, seed_path: str | Path):
        self._path = Path(seed_path)

    def _load(self) -> list[dict]:
        if not self._path.exists():
            return []
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            return []

    def _save(self, seeds: list[dict]):
        self._path.write_text(json.dumps(seeds, ensure_ascii=False, indent=2), encoding="utf-8")

    def submit(self, prompt_text: str, result_prompt: str, good: bool, source: str = "user-feedback"):
        prompt_text = str(prompt_text or "").strip()
        result_prompt = str(result_prompt or "").strip()
        if not prompt_text or not result_prompt:
            raise ValueError("prompt_text / result_prompt 不能为空")
        seeds = self._load()
        # 好反馈：结果提示词入种子（质量分 9）；坏反馈：源提示词质量分降级
        if good:
            import time
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
