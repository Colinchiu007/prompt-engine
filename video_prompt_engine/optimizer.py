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
from prompt_engine_core.text import strip_reasoning_blocks
from video_prompt_engine.config import load_config
from video_prompt_engine.strategies import get_strategy
from video_prompt_engine.llm import BaseVideoLLMProvider
from video_prompt_engine.prompt_builder import VideoPromptBuilder
from video_prompt_engine.rag_retriever import VideoRAGRetriever
from video_prompt_engine.cache_manager import VideoCacheManager
from video_prompt_engine.classifier import classify, suggest_dimensions
from video_prompt_engine.evaluator import evaluate, select_best
from video_prompt_engine.knowledge.loader import load_keywords_video
from video_prompt_engine.refined_blocks import DRIFT_TRAILER_RE, TRAILER_TAIL_RE

logger = logging.getLogger(__name__)

# 与策略 Output Format 同源（VIDEO_OUTPUT_KEYS），禁止双份手写漂移（C5）
def _json_retry_keys(tier: str) -> str:
    keys = list(VIDEO_OUTPUT_KEYS)
    if tier == "refined":
        # 评审 W2：refined 层策略样例含 blocks 键，重试提示必须同源，否则重试会引导 LLM 丢弃 blocks
        keys.append("blocks")
    return ", ".join('"' + k + '"' for k in keys)


def build_json_retry_hint(tier: str = "batch") -> str:
    """结构化输出重试提示（tier 感知 keys；batch 恒等于 JSON_RETRY_HINT 保持兼容）。"""
    return (
        "\n\nIMPORTANT: Your previous output was NOT a valid strict JSON object. "
        "Output ONLY a strict JSON object with EXACTLY these keys: "
        + _json_retry_keys(tier)
        + ". "
        "No markdown fences, no code blocks, no extra text outside the JSON object."
    )


JSON_RETRY_HINT = build_json_retry_hint("batch")


def strip_rendered_trailer(optimized: str, tail: str) -> str:
    """C6 尾行剥离（可测单元）：从「最后一段内以尾行形态存在」的 Photoreal NON-IP 起剥离到串尾。

    兼容旧形态 `{audio} only.` 与 Round3 Audio 段形态（Audio: ... / No music. 结尾）；
    尾行形态判定限定在最后一段（\n\n 块分隔之后，评审 C1-1）——正文中段字面量（如
    "Photoreal NON-IP aesthetic with deep blacks"）即使后接 only./Audio:/No music. 结尾
    也不跨块吸收，FINAL FRAME 等后续块不误删（评审 Warning-5 口径延续）。
    残缺裸尾行（以 NON-IP. 收尾的短残片，评审 C1-2）同样剥离，防 append 后双尾行残留。
    无尾行形态时回退 endswith(tail) 精确剥离；两者都不中 → 原样返回（调用方自行截断）。
    """
    import re
    blocks = re.split(r"\n\s*\n", optimized)
    last_block = blocks[-1]
    m = TRAILER_TAIL_RE.search(last_block)
    if m:
        body = optimized[: len(optimized) - len(last_block) + m.start()].rstrip()
        return re.sub(r"\n\s*$", "", body)
    m = DRIFT_TRAILER_RE.search(last_block)
    if m:
        # 评审 C3：漂移尾行（缺 aspect/duration 的 Photoreal NON-IP 形态）→ 剥离防双尾行
        body = optimized[: len(optimized) - len(last_block) + m.start()].rstrip()
        return re.sub(r"\n\s*$", "", body)
    marker = re.search(r"Photoreal\.?\s+NON-IP\.?", last_block, flags=re.IGNORECASE)
    if marker:
        # 评审 C1-2：残缺裸尾行（Photoreal...NON-IP 后无 only./Audio/No music 且以句点收尾、
        # 单行残片）→ 剥离防双尾行；中段字面量（后接描述性正文）不以 NON-IP. 结尾 → 保留
        suffix = last_block[marker.start():]
        if "\n" not in suffix and re.search(r"non-ip\.\s*$", suffix, flags=re.IGNORECASE):
            body = optimized[: len(optimized) - len(last_block) + marker.start()].rstrip()
            return re.sub(r"\n\s*$", "", body)
    if tail and optimized.endswith(tail):
        return optimized[: -len(tail)].rstrip()
    return optimized


def fit_refined_trailer(optimized: str, tail: str, max_length: int) -> str:
    """Fit a refined body plus its complete trailer inside max_length.

    The separator is part of the budget. If the complete trailer leaves no
    room for meaningful body content, fail closed instead of returning an
    overlong or trailer-only prompt.
    """
    try:
        limit = int(max_length)
    except (TypeError, ValueError) as error:
        raise ValueError("max_length must be an integer") from error
    trailer = str(tail or "").strip()
    body = strip_rendered_trailer(str(optimized or ""), trailer).strip()
    separator = " "
    if not trailer or limit <= len(trailer) + len(separator):
        raise ValueError("refined trailer cannot fit within max_length")
    body_budget = limit - len(trailer) - len(separator)
    fitted_body = body[:body_budget].rstrip()
    if not fitted_body:
        raise ValueError("refined prompt body cannot fit within max_length")
    return fitted_body + separator + trailer


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
            "HIGGSFIELD_FMT_V4",  # 版本盐：V4 = Round3 B/C（承接段/块骨架输出形态变化），旧缓存一次失效重建（V2→V4 同批发布）
            str(platform),
            lang,
            _h(request.prompt),
            _h(request.style or ""),
            str(request.creative_level),
            str(request.max_length),
            str(request.num_candidates),
            _h(request.negative_prompt or ""),
            ctx_hash,
            _h(request.prev_final_frame or ""),  # Round3 B：跨镜终态影响输出，必须入 key
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
            # Round3 B：跨镜承接指令段（仅 prev_final_frame 提供时注入；refined/batch 双形态）
            system_prompt += self._builder.build_continuity_section(request.prev_final_frame, tier)
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
                        system_prompt + build_json_retry_hint(tier), request.prompt, variant=i + 100 * retried,
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
                            # C6 尾行剥离：取末位 Photoreal NON-IP（评审 Warning-5：blocks 中段字面量不误剥；C1 双尾行防护）
                            # 评审 W3：fit 失败（body 空/预算过小）→ 截断降级，不整单失败
                            try:
                                optimized = fit_refined_trailer(optimized, tail, request.max_length)
                            except ValueError:
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

            # Round3 B：角色白名单（context.character_list 角色名，continuity_check 硬判据用）
            character_list: list[str] = []
            if request.context:
                cl = request.context.get("character_list")
                if isinstance(cl, list):
                    character_list = [
                        str(c.get("name", "")).strip() if isinstance(c, dict) else str(c).strip()
                        for c in cl if (c.get("name") if isinstance(c, dict) else c)
                    ]

            # 多候选择优：与 select_best 相同择优语义（分数降序 → 同分违规少者胜 → 仍同分先出现），
            # 内联排序保证 optimized 与 final_candidates[0] 一致（评审复验 Info）
            if len(candidates) > 1:
                scored = []
                for _idx, (_p, _m) in enumerate(candidates):
                    _info = evaluate(
                        _p, _m, source_prompt=request.prompt, language=lang, tier=tier,
                        max_length=request.max_length, prev_final_frame=request.prev_final_frame,
                        character_list=character_list,
                    )
                    scored.append((_info["score"], sum(abs(v) for v in (_info.get("violations") or {}).values()), _idx, _p, _m))
                scored.sort(key=lambda x: (-x[0], x[1], x[2]))
                optimized, video_meta = scored[0][3], scored[0][4]
                final_candidates = [x[3] for x in scored]
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
