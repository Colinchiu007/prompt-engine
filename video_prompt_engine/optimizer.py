"""视频引擎编排器 — 缓存 → 策略 → system prompt → context → RAG few-shot → LLM → 结构化后处理。

机制复刻图片引擎 Optimizer，独立实现；视频引擎专用（不 import prompt_engine）。
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from video_prompt_engine.models import (
    VideoOptimizeRequest, VideoOptimizeResult, VideoPromptMeta,
    normalize_video_platform, assert_no_sensitive_context, CONTEXT_KEYS,
)
from video_prompt_engine.config import load_config
from video_prompt_engine.strategies import get_strategy
from video_prompt_engine.llm import BaseVideoLLMProvider
from video_prompt_engine.prompt_builder import VideoPromptBuilder
from video_prompt_engine.rag_retriever import VideoRAGRetriever
from video_prompt_engine.knowledge.loader import load_keywords_video

logger = logging.getLogger(__name__)


def strip_reasoning_blocks(text: str) -> str:
    """剥离模型输出中的推理块（<think>...</think>），返回实际提示词内容。

    带推理能力的模型（如 MiniMax-M2.7）可能把思考过程写进返回内容：
    - 完整推理块 <think>...</think>：移除后保留 </think> 之后的内容；
    - 无闭合标签的 <think> 前缀：视为没有实际内容，返回空串（由调用方回退原文）。
    """
    if not text:
        return text
    import re
    stripped = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    lower = stripped.lower()
    think_idx = lower.find("<think>")
    if think_idx >= 0:
        stripped = stripped[:think_idx]
    return stripped.strip()


class VideoOptimizer:
    """视频提示词优化编排器。"""

    def __init__(self, config: Optional[dict] = None):
        self.config = config or load_config()
        self._provider = BaseVideoLLMProvider(self.config)
        self._rag = VideoRAGRetriever(self.config)
        self._builder = VideoPromptBuilder()
        self._cache: dict[str, VideoOptimizeResult] = {}
        self._keywords: dict[str, list[dict]] = {}
        self._load_keywords()

    def _load_keywords(self):
        from pathlib import Path
        path = Path(__file__).parent / "knowledge" / "keywords_video.json"
        if path.exists():
            try:
                self._keywords = load_keywords_video(path)
            except Exception as e:
                logger.warning("keywords load failed: %s", e)

    def keywords_hint(self, prompt: str, limit_per_dim: int = 6) -> str:
        """命中关键词词典 → 生成视频维度提示（镜头/运镜/光影/色彩/风格/场景/动作）。"""
        if not self._keywords:
            return ""
        lower = prompt.lower()
        hits = {}
        for dim, entries in self._keywords.items():
            for entry in entries[:limit_per_dim]:
                zh = (entry.get("zh") or "").lower()
                en = (entry.get("en") or "").lower()
                if zh and zh in lower or en and en in lower:
                    hits.setdefault(dim, []).append(f"{zh or en}({en or zh})")
                    if len(hits[dim]) >= 3:
                        break
        if not hits:
            return ""
        lines = [f"- {dim}: {', '.join(names)}" for dim, names in hits.items()]
        return "\n".join(lines)

    def _warn_unknown_context_keys(self, context) -> None:
        if not context or not isinstance(context, dict):
            return
        unknown = sorted(set(context.keys()) - set(CONTEXT_KEYS))
        for key in unknown:
            logger.warning("unknown context key ignored: %s", key)

    def _cache_key(self, request: VideoOptimizeRequest) -> str:
        return f"{request.platform.value if hasattr(request.platform, 'value') else request.platform}|{request.prompt}|{request.creative_level}|{request.max_length}"

    def optimize(self, request: VideoOptimizeRequest) -> VideoOptimizeResult:
        start = time.time()
        try:
            platform = normalize_video_platform(request.platform)
            # context 敏感键拦截
            if request.context:
                assert_no_sensitive_context(request.context)
                self._warn_unknown_context_keys(request.context)

            cache_key = self._cache_key(request)
            if cache_key in self._cache:
                return self._cache[cache_key]

            strategy_cls = get_strategy(platform) or get_strategy("generic_video")
            hint = self.keywords_hint(request.prompt)
            system_prompt = self._builder.build_system_prompt(
                strategy_cls,
                style=request.style,
                creative_level=request.creative_level,
                max_length=request.max_length,
                negative_prompt=request.negative_prompt,
                keywords_hint=hint,
            )
            system_prompt += self._builder.build_context_section(request.context)
            few_shot = self._rag.retrieve_few_shot(request)
            if few_shot:
                system_prompt += few_shot

            candidates = []
            video_meta = {}
            for i in range(request.num_candidates):
                raw, _tokens = self._provider.call(system_prompt, request.prompt, variant=i)
                raw = strip_reasoning_blocks(raw)
                if not raw:
                    optimized = request.prompt
                    video_meta = {}
                    candidates.append(optimized)
                    continue
                optimized, video_meta = strategy_cls.post_process_video(raw, creative_level=request.creative_level)
                if len(optimized) > request.max_length:
                    optimized = optimized[:request.max_length]
                if not optimized.strip():
                    optimized = request.prompt
                    video_meta = {}
                candidates.append(optimized)

            result = VideoOptimizeResult(
                optimized_prompt=candidates[0],
                platform=platform,
                style=request.style,
                model_used=self._provider.model_name,
                tokens_used=0,
                duration_ms=round((time.time() - start) * 1000, 1),
                candidates=candidates if request.num_candidates > 1 else [],
                video=VideoPromptMeta(**video_meta) if video_meta else None,
            )
            if len(self._cache) >= int(self.config.get("optimizer", {}).get("cache_size", 512)):
                self._cache.clear()
            self._cache[cache_key] = result
            return result
        except Exception as e:
            logger.error("video optimize failed: %s", e)
            return VideoOptimizeResult(
                optimized_prompt="",
                platform=normalize_video_platform(request.platform),
                style=request.style,
                model_used=self._provider.model_name,
                duration_ms=round((time.time() - start) * 1000, 1),
                error=str(e),
            )

    def optimize_batch(self, requests: list[VideoOptimizeRequest]) -> list[VideoOptimizeResult]:
        """批量优化：线程池有界并发 8，结果顺序与请求一致。"""
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=8) as pool:
            return list(pool.map(self.optimize, requests))
