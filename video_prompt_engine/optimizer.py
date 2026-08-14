"""视频引擎编排器 — 缓存 → 策略 → system prompt → context → RAG few-shot → LLM → 结构化后处理。

机制复刻图片引擎 Optimizer，独立实现；视频引擎专用（不 import prompt_engine）。

增强（video-prompt-engine-enhancement）：
- 双级缓存（内存 + SQLite）：key=platform|prompt|creative_level|max_length|language|num_candidates|negative_prompt|context_hash
- JSON 结构化输出失败重试（≤max_retries，带"只输出严格 JSON"提示，耗尽回退原文并标记）
- 输入分类（题材/镜头意图）→ 注入提示 + 关键词维度建议
- 多候选 evaluator 择优（num_candidates>1）
- output_language=zh 中文输出支持
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Optional

from video_prompt_engine.models import (
    VideoOptimizeRequest, VideoOptimizeResult, VideoPromptMeta,
    normalize_video_platform, assert_no_sensitive_context, CONTEXT_KEYS,
    VIDEO_OUTPUT_KEYS,
)
from video_prompt_engine.config import load_config
from video_prompt_engine.strategies import get_strategy
from video_prompt_engine.llm import BaseVideoLLMProvider
from video_prompt_engine.prompt_builder import VideoPromptBuilder
from video_prompt_engine.rag_retriever import VideoRAGRetriever
from video_prompt_engine.cache_manager import VideoCacheManager
from video_prompt_engine.classifier import classify, suggest_dimensions
from video_prompt_engine.evaluator import evaluate, select_best
from video_prompt_engine.knowledge.loader import load_keywords_video

logger = logging.getLogger(__name__)

# 与策略 Output Format 同源（VIDEO_OUTPUT_KEYS），禁止双份手写漂移（C5）
_JSON_RETRY_KEYS = ", ".join('"' + k + '"' for k in VIDEO_OUTPUT_KEYS)

JSON_RETRY_HINT = (
    "\n\nIMPORTANT: Your previous output was NOT a valid strict JSON object. "
    "Output ONLY a strict JSON object with EXACTLY these keys: "
    + _JSON_RETRY_KEYS
    + ". "
    "No markdown fences, no code blocks, no extra text outside the JSON object."
)


def derive_character_count(context: Optional[dict]) -> Optional[int]:
    """从 context 推导画面角色数：character_list 长度优先，character 单角色兜底。"""
    if not context or not isinstance(context, dict):
        return None
    cl = context.get("character_list")
    if isinstance(cl, list) and len(cl) > 0:
        return len(cl)
    if context.get("character"):
        return 1
    return None


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

    @staticmethod
    def _safe_int(value, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def __init__(self, config: Optional[dict] = None, cache_dir: Optional[str] = None):
        self.config = config or load_config()
        self._provider = BaseVideoLLMProvider(self.config)
        self._rag = VideoRAGRetriever(self.config)
        self._builder = VideoPromptBuilder()
        cache_cfg = self.config.get("cache", {})
        if cache_cfg.get("enabled", True):
            from pathlib import Path
            persist = cache_dir or cache_cfg.get("dir", "video_prompt_cache")
            p = Path(persist)
            if not p.is_absolute():
                p = Path(__file__).parent.parent / p
            self._cache_mgr = VideoCacheManager(p, memory_size=int(cache_cfg.get("memory_size", 512)))
        else:
            self._cache_mgr = None
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

    def _cache_key(self, request: VideoOptimizeRequest, platform: str, lang: str) -> str:
        """缓存 key：对每个可变组件做 sha1 哈希后拼接，避免 `|` 碰撞并覆盖全部影响结果的参数。"""
        def _h(value: str) -> str:
            return hashlib.sha1(str(value or "").encode("utf-8")).hexdigest()[:16]
        ctx_hash = ""
        if request.context:
            ctx_hash = hashlib.sha1(
                json.dumps(request.context, sort_keys=True, ensure_ascii=False).encode("utf-8")
            ).hexdigest()[:16]
        return "|".join([
            "HIGGSFIELD_FMT_V1",  # 版本盐：Output Format/尾行机制变化时旧缓存天然失效（C4）
            str(platform),
            lang,
            _h(request.prompt),
            _h(request.style or ""),
            str(request.creative_level),
            str(request.max_length),
            str(request.num_candidates),
            _h(request.negative_prompt or ""),
            ctx_hash,
        ])

    @staticmethod
    def _build_classification_section(classification: dict, dims: list[str]) -> str:
        if not classification:
            return ""
        genres = classification.get("genres") or []
        intents = classification.get("shot_intents") or []
        if not genres and not intents:
            return ""
        lines = ["\n## 输入题材/镜头意图检测（仅供参考，不得改变事实）"]
        if genres:
            lines.append(f"- 题材(genre): {', '.join(genres)}")
        if intents:
            lines.append(f"- 镜头意图(shot intent): {', '.join(intents)}")
        if dims:
            lines.append(f"- 建议关键词维度: {', '.join(dims)}")
        return "\n".join(lines)
    def optimize(self, request: VideoOptimizeRequest) -> VideoOptimizeResult:
        start = time.time()
        try:
            platform = normalize_video_platform(request.platform)
            # context 敏感键拦截
            if request.context:
                assert_no_sensitive_context(request.context)
                self._warn_unknown_context_keys(request.context)

            lang = "zh" if str(getattr(request, "output_language", "en") or "en").lower().startswith("zh") else "en"
            # tier 层级：creative_level≥7 → refined（导演工作流/尾行/5000 上限）；否则 batch（无尾行）
            tier = "refined" if request.creative_level >= 7 else "batch"
            cache_key = self._cache_key(request, platform, lang)

            # 双级缓存命中（跳过 LLM）
            if self._cache_mgr is not None:
                cached = self._cache_mgr.get(cache_key)
                if cached:
                    hit = dict(cached)  # 拷贝，避免变异缓存内共享对象
                    hit["cache_hit"] = True
                    hit["duration_ms"] = round((time.time() - start) * 1000, 1)
                    return VideoOptimizeResult(**hit)

            strategy_cls = get_strategy(platform) or get_strategy("generic_video")
            classification = classify(request.prompt)
            dims = suggest_dimensions(request.prompt)
            hint = self.keywords_hint(request.prompt)
            system_prompt = self._builder.build_system_prompt(
                strategy_cls,
                style=request.style,
                creative_level=request.creative_level,
                max_length=request.max_length,
                negative_prompt=request.negative_prompt,
                keywords_hint=hint,
                output_language=lang,
                tier=tier,
                character_count=derive_character_count(request.context),
            )
            system_prompt += self._build_classification_section(classification, dims)
            system_prompt += self._builder.build_context_section(request.context)
            few_shot = self._rag.retrieve_few_shot(request, platform=platform)
            if few_shot:
                system_prompt += few_shot

            max_retries = max(0, self._safe_int(self.config.get("optimizer", {}).get("max_retries", 2), 2))
            candidates: list[tuple[str, dict]] = []
            total_retried = 0
            for i in range(request.num_candidates):
                raw, _tokens = self._provider.call(system_prompt, request.prompt, variant=i, max_length=request.max_length)
                raw = strip_reasoning_blocks(raw)
                retried = 0
                # JSON 结构化输出失败 → 带"只输出严格 JSON"提示重试（≤max_retries）
                while raw and strategy_cls.parse_video_json(raw) is None and retried < max_retries:
                    retried += 1
                    total_retried += 1
                    raw, _tokens = self._provider.call(
                        system_prompt + JSON_RETRY_HINT, request.prompt, variant=i + 100 * retried,
                        max_length=request.max_length,
                    )
                    raw = strip_reasoning_blocks(raw)
                if raw and strategy_cls.parse_video_json(raw) is not None:
                    optimized, video_meta = strategy_cls.post_process_video(raw, creative_level=request.creative_level, tier=tier)
                    # C6 尾行生命周期：body 预算 = max_length − len(tail)，tail 永不截断
                    if len(optimized) > request.max_length:
                        tail = strategy_cls.build_tail(video_meta) if tier == "refined" else ""
                        if tail:
                            # 剥离已存在尾行（LLM 直出或 append，格式可能漂移：5.5s/小写/Photoreal 缺句点）→ body 截断 → 重 append 规范尾行
                            import re
                            body = re.sub(
                                r"\s*Photoreal\.?\s+NON-IP\.?\s+.*?only\.?\s*$", "",
                                optimized, flags=re.IGNORECASE | re.DOTALL,
                            )
                            if body == optimized and optimized.endswith(tail):
                                body = optimized[: -len(tail)]
                            if body.strip():
                                optimized = body[: max(0, request.max_length - len(tail))] + tail
                            else:
                                optimized = optimized[:request.max_length]
                        else:
                            optimized = optimized[:request.max_length]
                    if not optimized.strip():
                        optimized = request.prompt
                        video_meta = {}
                else:
                    # 重试耗尽 → 回退原文（保持内容保真）
                    optimized = request.prompt
                    video_meta = {}
                candidates.append((optimized, video_meta))

            # 多候选择优：evaluator 评分，最优在前
            if len(candidates) > 1:
                scored = [
                    (evaluate(p, m, source_prompt=request.prompt, language=lang, tier=tier, max_length=request.max_length)["score"], p, m)
                    for p, m in candidates
                ]
                scored.sort(key=lambda x: x[0], reverse=True)
                optimized, video_meta = scored[0][1], scored[0][2]
                final_candidates = [p for _, p, _ in scored]
            else:
                optimized, video_meta = candidates[0]
                final_candidates = []

            # W6：meta 归一遗漏导致 pydantic 校验失败 → 回退原文并标记，不整单失败
            try:
                meta_model = VideoPromptMeta(**video_meta) if video_meta else None
            except Exception as e:
                logger.warning("video meta validation failed, falling back to source: %s", e)
                optimized = request.prompt
                final_candidates = []
                meta_model = None
            result = VideoOptimizeResult(
                optimized_prompt=optimized,
                platform=platform,
                style=request.style,
                model_used=self._provider.model_name,
                tokens_used=0,
                duration_ms=round((time.time() - start) * 1000, 1),
                candidates=final_candidates,
                video=meta_model,
                language=lang,
                retried=total_retried,
                classification=classification,
            )
            if self._cache_mgr is not None:
                self._cache_mgr.set(cache_key, result.model_dump(exclude_none=True))
            return result
        except Exception as e:
            logger.error("video optimize failed: %s", e)
            return VideoOptimizeResult(
                optimized_prompt="",
                platform=normalize_video_platform(request.platform),
                style=request.style,
                model_used=self._provider.model_name,
                duration_ms=round((time.time() - start) * 1000, 1),
                language="zh" if str(getattr(request, "output_language", "en") or "en").lower().startswith("zh") else "en",
                error=str(e),
            )

    def optimize_batch(self, requests: list[VideoOptimizeRequest]) -> list[VideoOptimizeResult]:
        """批量优化：线程池有界并发 8，结果顺序与请求一致。"""
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=8) as pool:
            return list(pool.map(self.optimize, requests))

    def cache_stats(self) -> dict:
        """缓存统计（API /v1/video/cache/stats 使用）。"""
        if self._cache_mgr is None:
            return {"enabled": False}
        return {"enabled": True, **self._cache_mgr.stats()}
