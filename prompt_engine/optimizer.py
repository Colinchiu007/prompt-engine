"""Optimizer — 核心编排器（支持 RAG few-shot 注入）"""
import logging
import re
import threading
import time
from pathlib import Path
from typing import Optional

from prompt_engine.models import (
    OptimizeRequest, OptimizeResult, ReverseRequest, ReverseResult,
    StyleCategory, StyleType, StyleCategoryResult,
    DomainType, VideoPromptResult, OptimizationStrategy,
)
from prompt_engine.config import load_config
from prompt_engine.strategies import get_strategy
from prompt_engine_core.text import strip_reasoning_blocks
from prompt_engine.llm.base import BaseLLMProvider
from prompt_engine.rewriter import PromptRewriter
from prompt_engine.disturb import PromptDisturber
from prompt_engine.classifier import StyleCategoryClassifier

# ── 新模块导入 ──────────────────────────────────────────────────────────
from prompt_engine.cache_manager import (
    _PromptCache,  # noqa: F401 — re-export backward compat
    _legacy_similarity,  # noqa: F401
    fuzzy_match_prompt,  # noqa: F401
    CacheManager,
)
from prompt_engine.cache_manager import similarity as _similarity  # noqa: F811 — backward compat alias
from prompt_engine.style_detector import (
    _STYLE_TYPE_KEYWORDS,  # noqa: F401
    detect_style_type_from_category as _detect_style_type_from_category,
    style_category_to_db_key as _style_category_to_db_key,
    get_preferred_db_keys as _get_preferred_db_keys,
)
from prompt_engine.llm_caller import LLMCaller
from prompt_engine.rag_retriever import RAGRetriever
from prompt_engine.prompt_builder import PromptBuilder

logger = logging.getLogger(__name__)


def requires_llm(request: OptimizeRequest) -> bool:
    """判断请求是否必须调用 LLM（用于 rest 边界 BYOK fail-closed）。

    策略只由 optimization_strategy 决定；creative_level 不参与执行路径路由。
    """
    return resolve_optimization_strategy(request) == OptimizationStrategy.LLM


def _request_caller(request) -> str | None:
    """Return the product identifier carried by the request's BYOK binding."""
    llm = getattr(request, "llm", None)
    return getattr(llm, "caller", None) if llm is not None else None


def resolve_optimization_strategy(request: OptimizeRequest) -> OptimizationStrategy:
    """解析请求实际执行路径，并拒绝未知策略与视频模板路径。"""
    try:
        strategy = OptimizationStrategy(request.optimization_strategy)
    except (TypeError, ValueError) as exc:
        raise ValueError("optimization_strategy 必须是 template 或 llm") from exc
    if strategy == OptimizationStrategy.LLM:
        return OptimizationStrategy.LLM
    if strategy == OptimizationStrategy.TEMPLATE:
        if request.domain == DomainType.VIDEO:
            raise ValueError("video 域不支持 template 优化策略")
        return OptimizationStrategy.TEMPLATE
    raise ValueError("optimization_strategy 必须是 template 或 llm")


class Optimizer:
    """提示词优化引擎核心编排器

    职责：编排 5 个子模块完成 prompt 优化全流程
      - CacheManager: 双级缓存
      - LLMCaller: LLM 调用封装
      - RAGRetriever: RAG 知识库检索
      - PromptBuilder: 模板渲染 + 系统提示词构建
      - StyleCategoryClassifier: 风格分类（直接持有）
    """

    def __init__(self, config: Optional[dict] = None):
        self.config = config or load_config()
        self._cat_classifier = StyleCategoryClassifier()
        self._cache = CacheManager()
        self._rag = RAGRetriever(self.config)
        self._prompt_builder = PromptBuilder()
        # 线程本地：per-request BYOK provider（batch 并发时各线程独立，不污染单例）
        self._local = threading.local()

    # ── 向后兼容属性 ────────────────────────────────────────────

    @property
    def _sqlite_cache(self):
        return self._cache.sqlite_cache

    @property
    def _mem_cache(self):
        return self._cache.mem_cache

    # ── 模板渲染 ────────────────────────────────────────────────

    def _render_from_template(self, request: OptimizeRequest) -> OptimizeResult:
        """模板执行路径直出，不调用 LLM。"""
        return PromptBuilder.render_from_template(request)

    # ── RAG 检索 ────────────────────────────────────────────────

    def _init_knowledge(self) -> None:
        """初始化 RAG 知识库（RAGRetriever 初始化时已执行，此方法保留兼容）"""
        pass

    def _retrieve_few_shot(self, request: OptimizeRequest) -> str:
        """检索相似 prompt 作为 few-shot 示例"""
        return self._rag.retrieve_few_shot(request)

    # ── LLM 调用 ────────────────────────────────────────────────

    def _call_llm(self, system_prompt: str, user_prompt: str, variant: int = 0) -> tuple[str, int]:
        """调用 LLM（BYOK：优先使用当前请求线程绑定的 llm_caller）"""
        caller = getattr(self._local, "llm_caller", None)
        if caller is None:
            raise RuntimeError("未配置 LLM provider：请通过请求 llm 对象传入调用方模型绑定（BYOK）")
        return caller.call(system_prompt, user_prompt, variant)

    def _call_vision_llm(self, system_prompt: str, image_url: str, detail: str = "auto") -> tuple[str, int]:
        """调用当前请求绑定的视觉 LLM 分析图片。"""
        caller = getattr(self._local, "llm_caller", None)
        if caller is None:
            raise RuntimeError("未配置 LLM provider：请通过请求 llm 对象传入调用方模型绑定（BYOK）")
        return caller.call_vision(system_prompt, image_url, detail)

    # ── 缓存：通过 CacheManager 代理 ──────────────────────────

    def _cache_key(self, prompt: str, platform: str, creative_level: int,
                   max_length: int, negative_prompt: str, num_candidates: int,
                   excluded_characters=None, no_swap_pairs=None,
                   context=None, style=None, language: str = "en",
                   provider: str = "", domain: str = "image",
                   optimization_strategy: str = "llm") -> str:
        return self._cache.make_key(prompt, platform, creative_level, max_length, negative_prompt, num_candidates,
                                    excluded_characters=excluded_characters, no_swap_pairs=no_swap_pairs,
                                    context=context, style=style, language=language, provider=provider,
                                    domain=domain, optimization_strategy=optimization_strategy)

    def _cache_get(self, prompt: str, platform: str, creative_level: int,
                   max_length: int, negative_prompt: str, num_candidates: int,
                   excluded_characters=None, no_swap_pairs=None,
                   context=None, style=None, language: str = "en",
                   provider: str = "", domain: str = "image",
                   optimization_strategy: str = "llm") -> Optional[OptimizeResult]:
        """双级缓存读取：L1 内存 → L2 SQLite（预热 L1）"""
        return self._cache.get(prompt, platform, creative_level, max_length, negative_prompt, num_candidates,
                               excluded_characters=excluded_characters, no_swap_pairs=no_swap_pairs,
                               context=context, style=style, language=language, provider=provider,
                               domain=domain, optimization_strategy=optimization_strategy)

    def _cache_set(self, prompt: str, platform: str, creative_level: int,
                   max_length: int, negative_prompt: str, num_candidates: int,
                   result: OptimizeResult,
                   excluded_characters=None, no_swap_pairs=None,
                   context=None, style=None, language: str = "en",
                   provider: str = "", domain: str = "image",
                   optimization_strategy: str = "llm"):
        """写入双级缓存"""
        self._cache.set(prompt, platform, creative_level, max_length, negative_prompt, num_candidates, result,
                        excluded_characters=excluded_characters, no_swap_pairs=no_swap_pairs,
                        context=context, style=style, language=language, provider=provider,
                        domain=domain, optimization_strategy=optimization_strategy)

    # ── 核心编排方法 ───────────────────────────────────────────


    @staticmethod
    def _warn_unknown_context_keys(context) -> None:
        """context 白名单：未知键忽略并记录 warning（对齐 openspec video-content-fidelity）。"""
        import logging
        if not context or not isinstance(context, dict):
            return
        known = {"synopsis", "character", "setting", "character_list", "narrative_intent", "scene_type", "full_text"}
        unknown = sorted(set(context.keys()) - known)
        for key in unknown:
            logging.getLogger("prompt_engine.optimizer").warning("unknown context key ignored: %s", key)

    def optimize(self, request: OptimizeRequest, provider: Optional[BaseLLMProvider] = None,
                provider_id: str = "") -> OptimizeResult:
        """单条提示词优化主流程

        BYOK：provider 为调用方经 llm 对象构建的 provider（REST/MCP 层传入）；
        LLM 执行路径没有 provider 时 fail-closed，不回退服务端 config.yaml。
        provider_id 非空时并入缓存键（provider|model 身份），避免跨调用方共享缓存串模型元数据。
        """
        start_time = time.time()
        effective_provider = provider
        _bound_caller = False
        effective_strategy = None
        try:
            effective_strategy = resolve_optimization_strategy(request)
            if effective_strategy == OptimizationStrategy.LLM and effective_provider is None:
                raise RuntimeError(
                    "未配置 LLM provider：请通过请求 llm 对象传入调用方模型绑定（BYOK，引擎不再使用服务端 key 兜底）"
                )
            # 缓存以实际执行方式隔离；模板不消费调用方模型，因此不带 provider identity。
            cache_provider_id = provider_id if effective_strategy == OptimizationStrategy.LLM else ""
            # ✨ 双级缓存检查（SQLite + 内存）— Round3 T1：key 全组件化（约束/context/style/语言），防串号
            cache_language = "zh" if re.search(r"[一-鿿]", request.prompt) else "en"
            cache_style = request.style.value if request.style is not None else None
            cached = None
            if not request.bypass_cache:
                cached = self._cache_get(
                    request.prompt, request.platform.value,
                    request.creative_level, request.max_length,
                    request.negative_prompt or "", request.num_candidates,
                    excluded_characters=request.excluded_characters,
                    no_swap_pairs=request.no_swap_pairs,
                    context=request.context,
                    style=cache_style,
                    language=cache_language,
                    provider=cache_provider_id,
                    domain=request.domain.value,
                    optimization_strategy=effective_strategy.value,
                )
            if cached:
                logger.info("Cache hit: %s @ %s", request.prompt[:50], request.platform.value)
                cached = cached.model_copy(deep=True)
                cached.key_source = "caller" if effective_strategy == OptimizationStrategy.LLM else "none"
                cached.strategy_used = effective_strategy.value
                cached.caller = _request_caller(request)
                cached.cache_hit = True
                if effective_strategy == OptimizationStrategy.LLM and effective_provider is not None:
                    cached.model_used = effective_provider.model_name
                elif effective_strategy == OptimizationStrategy.TEMPLATE:
                    cached.model_used = "template"
                return cached

            # 模板策略直出（免 LLM）— 仅图片领域；视频领域必须使用 LLM 结构化输出。
            if effective_strategy == OptimizationStrategy.TEMPLATE:
                logger.info("Template render: creative_level=%d, %s @ %s",
                            request.creative_level, request.prompt[:50], request.platform.value)
                result = self._render_from_template(request)
                result.key_source = "none"
                result.strategy_used = OptimizationStrategy.TEMPLATE.value
                result.cache_hit = False
                if not request.bypass_cache:
                    self._cache_set(
                        request.prompt, request.platform.value,
                        request.creative_level, request.max_length,
                        request.negative_prompt or "", request.num_candidates,
                        result,
                        excluded_characters=request.excluded_characters,
                        no_swap_pairs=request.no_swap_pairs,
                        context=request.context,
                        style=cache_style,
                        language=cache_language,
                        provider=cache_provider_id,
                        domain=request.domain.value,
                        optimization_strategy=effective_strategy.value,
                    )
                return result

            # BYOK per-request caller：绑定到当前线程，_call_llm 优先使用；finally 清理防跨请求串用
            self._local.llm_caller = LLMCaller(effective_provider)
            _bound_caller = True
            logger.info(
                "LLM path: model=%s provider=%s creative_level=%d max_length=%d "
                "platform=%s style=%s num_candidates=%d domain=%s",
                effective_provider.model_name, effective_provider.__class__.__name__,
                request.creative_level, request.max_length,
                request.platform.value, request.style.value if request.style else "None",
                request.num_candidates, request.domain.value,
            )

            detected_result: Optional[StyleCategoryResult] = None

            # 0. 自动风格检测（当 style 未指定时）
            effective_style = request.style
            if request.auto_detect_style and request.style is None:
                detected_result = self._cat_classifier.classify(
                    request.prompt, max_categories=5, use_llm=False,
                )
                if detected_result and detected_result.categories:
                    detected_style, detected_result = _detect_style_type_from_category(
                        detected_result, request.prompt,
                    )
                    if detected_style:
                        effective_style = detected_style
                        logger.info(
                            "Auto-detected style: %s from MJ categories: %s",
                            detected_style.value,
                            [c.value for c in detected_result.categories],
                        )

            # 1. 加载平台策略（视频领域未知平台回退 generic_video）
            strategy_cls = get_strategy(request.platform.value)
            if not strategy_cls:
                strategy_cls = get_strategy("generic_video" if request.domain == DomainType.VIDEO else "generic")

            # 2. 构建系统提示词
            system_prompt = PromptBuilder.build_system_prompt(
                strategy_cls,
                style=effective_style,
                creative_level=request.creative_level,
                max_length=request.max_length,
                negative_prompt=request.negative_prompt,
            )
            logger.info("System prompt: len=%d style=%s creative_level=%d",
                        len(system_prompt), effective_style.value if effective_style else "None",
                        request.creative_level)

            # 2.5 PROJECT-012 上下文注入（角色一致性）
                        # video-content-fidelity S4b：context 白名单校验（未知键忽略 + warning，不改变优化行为）
            self._warn_unknown_context_keys(request.context)
            system_prompt += PromptBuilder.build_context_section(request.context)

            # 3. RAG few-shot 注入
            few_shot = self._retrieve_few_shot(request)
            if few_shot:
                system_prompt += few_shot

            # 4. 调用 LLM（单版本或多候选）
            num = request.num_candidates
            total_tokens = 0
            candidates = []
            is_video = request.domain == DomainType.VIDEO
            video_meta: dict = {}

            for i in range(num):
                logger.info("Candidate %d/%d: calling LLM variant=%d", i + 1, num, i)
                raw_output, tokens = "", 0
                stripped_output = ""
                # 推理模型（如 DeepSeek）可能只输出 <thinking> 思考块而不返回实际内容：
                # 剥离后为空时先有界重试（最多 3 次），仍为空则回退原文，
                # 保证引擎被其它项目作为独立服务调用时不因空结论整线失败。
                for empty_attempt in range(3):
                    raw_output, tokens = self._call_llm(
                        system_prompt, request.prompt, variant=i,
                    )
                    stripped_output = strip_reasoning_blocks(raw_output or "")
                    if stripped_output:
                        break
                    logger.warning(
                        "Candidate %d/%d attempt %d: LLM 剥离推理块后为空（原始长度=%d），重试",
                        i + 1, num, empty_attempt + 1, len(raw_output or ""),
                    )
                raw_output = stripped_output
                if not raw_output:
                    logger.warning("Candidate %d/%d: LLM 仍只返回推理/空内容，回退原文", i + 1, num)
                    candidates.append(request.prompt)
                    continue
                if is_video:
                    # 视频领域：结构化输出（渲染单串 + 结构化字段）
                    optimized, video_meta = strategy_cls.post_process_video(
                        raw_output,
                        creative_level=request.creative_level,
                    )
                else:
                    preferred_db_keys = _get_preferred_db_keys(detected_result)
                    optimized = strategy_cls.post_process(
                        raw_output,
                        creative_level=request.creative_level,
                        preferred_categories=preferred_db_keys or None,
                    )
                if len(optimized) > request.max_length:
                    optimized = optimized[:request.max_length]
                if not optimized or not optimized.strip():
                    logger.warning("Candidate %d/%d: 后处理结果为空，回退原文", i + 1, num)
                    candidates.append(request.prompt)
                    continue
                candidates.append(optimized)
                total_tokens += tokens

            elapsed = (time.time() - start_time) * 1000
            logger.info(
                "LLM completed: %d candidates, total_tokens=%d, elapsed=%dms",
                num, total_tokens, int(elapsed),
            )

            # 4.5 图片域多候选择优（Higgsfield 对齐 — spec: image-prompt-quality）：
            # 确定性启发式评分降序，最高分为主输出；单候选/视频 legacy 路径不接入（行为不变）。
            # 缓存 key 已含 num_candidates，择优不破坏缓存语义。
            if not is_video and num > 1:
                from prompt_engine.evaluator import evaluate_quality
                tier = "batch"
                language = "zh" if re.search(r"[\u4e00-\u9fff]", request.prompt) else "en"
                raw_excluded = request.excluded_characters
                if raw_excluded is None:
                    raw_excluded = []
                elif isinstance(raw_excluded, str):
                    raw_excluded = [raw_excluded]
                else:
                    raw_excluded = list(raw_excluded)
                meta = {
                    "excluded_characters": raw_excluded,
                    "no_swap_pairs": list(request.no_swap_pairs or []),
                }
                scored = sorted(
                    (
                        (
                            evaluate_quality(
                                p, meta, source_prompt=request.prompt,
                                language=language, tier=tier, max_length=request.max_length,
                            )["score"],
                            p,
                        )
                        for p in candidates
                    ),
                    key=lambda x: x[0],
                    reverse=True,
                )
                optimized_prompt = scored[0][1]
                ordered_candidates = [p for _, p in scored]
            else:
                optimized_prompt = candidates[0]
                ordered_candidates = candidates

            # 存入双级缓存以便下次命中
            result = OptimizeResult(
                optimized_prompt=optimized_prompt,
                platform=request.platform,
                style=effective_style if effective_style != request.style else request.style,
                model_used=effective_provider.model_name,
                tokens_used=total_tokens,
                duration_ms=round(elapsed, 1),
                candidates=ordered_candidates if num > 1 else [],
                detected_categories=detected_result,
                video=VideoPromptResult(**video_meta) if is_video and video_meta else None,
                key_source="caller",
                caller=_request_caller(request),
                strategy_used=OptimizationStrategy.LLM.value,
                cache_hit=False,
            )
            if not request.bypass_cache:
                self._cache_set(
                    request.prompt, request.platform.value,
                    request.creative_level, request.max_length,
                    request.negative_prompt or "", request.num_candidates,
                    result,
                    excluded_characters=request.excluded_characters,
                    no_swap_pairs=request.no_swap_pairs,
                    context=request.context,
                    style=cache_style,
                    language=cache_language,
                    provider=cache_provider_id,
                    domain=request.domain.value,
                    optimization_strategy=effective_strategy.value,
                )
            return result

        except Exception as e:
            elapsed = (time.time() - start_time) * 1000
            logger.error("optimize failed for prompt '%s': %s", request.prompt[:50], e)
            return OptimizeResult(
                optimized_prompt=request.prompt,
                platform=request.platform,
                style=request.style,
                model_used=effective_provider.model_name if effective_provider else "",
                tokens_used=0,
                duration_ms=round(elapsed, 1),
                error=str(e),
                strategy_used=effective_strategy.value if effective_strategy else None,
            )
        finally:
            if _bound_caller:
                try:
                    delattr(self._local, "llm_caller")
                except AttributeError:
                    pass

    def rewrite(
        self,
        request: OptimizeRequest,
        provider: Optional[BaseLLMProvider] = None,
        provider_id: str = "",
    ) -> OptimizeResult:
        """Prompt 扩写：只使用调用方传入的 BYOK provider。"""
        start_time = time.time()
        _bound_caller = False
        try:
            if provider is None:
                raise RuntimeError(
                    "未配置 LLM provider：请通过请求 llm 对象传入调用方模型绑定（BYOK，引擎不再使用服务端 key 兜底）"
                )
            self._local.llm_caller = LLMCaller(provider)
            _bound_caller = True
            rewriter = PromptRewriter(provider, max_retries=3)
            result_raw = strip_reasoning_blocks(rewriter.rewrite_raw(request.prompt)).strip()
            if not result_raw:
                raise RuntimeError("LLM 返回了空内容，未生成有效扩写结果")
            if len(result_raw) > request.max_length:
                result_raw = result_raw[:request.max_length]

            elapsed = (time.time() - start_time) * 1000
            return OptimizeResult(
                optimized_prompt=result_raw,
                platform=request.platform,
                style=request.style,
                model_used=provider.model_name,
                tokens_used=0,
                duration_ms=round(elapsed, 1),
                key_source="caller",
                strategy_used=OptimizationStrategy.LLM.value,
                caller=_request_caller(request),
                cache_hit=False,
                error=None,
            )
        except Exception as e:
            elapsed = (time.time() - start_time) * 1000
            logger.error("rewrite failed for prompt '%s': %s", request.prompt[:50], e)
            return OptimizeResult(
                optimized_prompt=request.prompt,
                platform=request.platform,
                style=request.style,
                model_used=provider.model_name if provider is not None else "",
                tokens_used=0,
                duration_ms=round(elapsed, 1),
                key_source="caller" if provider is not None else "none",
                strategy_used=OptimizationStrategy.LLM.value,
                caller=_request_caller(request),
                cache_hit=False,
                error=str(e),
            )
        finally:
            if _bound_caller:
                try:
                    delattr(self._local, "llm_caller")
                except AttributeError:
                    pass

    def disturb_and_optimize(
        self,
        request: OptimizeRequest,
        num_augmented: int = 3,
        strength: float = 0.3,
        provider: Optional[BaseLLMProvider] = None,
        provider_id: str = "",
    ) -> OptimizeResult:
        """扰动增强优化：对 prompt 做扰动后多次优化，取最佳"""
        import concurrent.futures
        start_time = time.time()
        effective_strategy = None
        try:
            effective_strategy = resolve_optimization_strategy(request)
            if effective_strategy == OptimizationStrategy.TEMPLATE:
                return self.optimize(request)
            if provider is None:
                return self.optimize(request, provider=None, provider_id=provider_id)
            model_name = getattr(provider, "model_name", "")
            disturb = PromptDisturber(strength=strength)
            perturbations = disturb.perturb(request.prompt)

            # 原始 + 多个扰动版本，并行优化（每次生成 num_augmented 个扰动）
            all_prompts = [request.prompt]
            for _ in range(num_augmented):
                all_prompts.append(disturb.perturb(request.prompt))

            def optimize_one(p: str) -> OptimizeResult:
                try:
                    sub_req = OptimizeRequest(
                        prompt=p,
                        domain=request.domain,
                        platform=request.platform,
                        style=request.style,
                        creative_level=request.creative_level,
                        optimization_strategy=request.optimization_strategy,
                        max_length=request.max_length,
                        negative_prompt=request.negative_prompt,
                        num_candidates=request.num_candidates,
                        auto_detect_style=request.auto_detect_style,
                        context=request.context,
                        excluded_characters=request.excluded_characters,
                        no_swap_pairs=request.no_swap_pairs,
                        bypass_cache=request.bypass_cache,
                        llm=request.llm,
                    )
                    return self._call_llm_with_timeout(
                        sub_req,
                        provider=provider,
                        provider_id=provider_id,
                        timeout_seconds=15,
                    )
                except Exception as e:
                    logger.warning("Sub-optimize failed for '%s': %s", p[:30], e)
                    return OptimizeResult(
                        optimized_prompt=p,
                        platform=request.platform,
                        error=str(e),
                    )

            # 并行执行，加超时保护（总共最多等 30 秒）
            all_results: list[OptimizeResult] = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(all_prompts)) as executor:
                futures = {executor.submit(optimize_one, p): p for p in all_prompts}
                try:
                    done, _ = concurrent.futures.wait(
                        futures.keys(),
                        timeout=30.0,
                        return_when=concurrent.futures.ALL_COMPLETED,
                    )
                    for future in done:
                        try:
                            all_results.append(future.result())
                        except Exception as e:
                            logger.warning("Future failed: %s", e)
                except Exception as e:
                    logger.warning("Parallel execution error: %s", e)

            # 选择最佳结果（非错误且最长的）
            best = None
            for r in all_results:
                if r.error:
                    continue
                if best is None or len(r.optimized_prompt) > len(best.optimized_prompt):
                    best = r

            if best is None:
                best = all_results[0] if all_results else OptimizeResult(
                    optimized_prompt=request.prompt,
                    platform=request.platform,
                    style=request.style,
                    model_used=model_name,
                    error="All optimize calls failed",
                )

            elapsed = (time.time() - start_time) * 1000
            # 合并 tokens
            total_tokens = sum(r.tokens_used for r in all_results)
            successful_results = [r for r in all_results if not r.error]
            cache_hit = (
                bool(successful_results)
                and len(successful_results) == len(all_results)
                and all(r.cache_hit for r in successful_results)
            )
            return OptimizeResult(
                optimized_prompt=best.optimized_prompt,
                platform=request.platform,
                style=request.style,
                model_used=model_name,
                tokens_used=total_tokens,
                duration_ms=round(elapsed, 1),
                candidates=[r.optimized_prompt for r in all_results if not r.error][:num_augmented],
                key_source="caller",
                strategy_used=effective_strategy.value,
                caller=_request_caller(request),
                cache_hit=cache_hit,
                error=best.error,
            )
        except Exception as e:
            elapsed = (time.time() - start_time) * 1000
            logger.error("disturb_and_optimize failed: %s", e)
            return OptimizeResult(
                optimized_prompt=request.prompt,
                platform=request.platform,
                style=request.style,
                model_used=model_name if provider is not None else "",
                tokens_used=0,
                duration_ms=round(elapsed, 1),
                strategy_used=effective_strategy.value if effective_strategy else None,
                error=str(e),
            )

    def reverse_engineer(
        self,
        request: ReverseRequest,
        provider: Optional[BaseLLMProvider] = None,
        provider_id: str = "",
    ) -> ReverseResult:
        """图片逆向工程：只使用调用方传入的 BYOK provider。"""
        start_time = time.time()
        _bound_caller = False
        try:
            if provider is None:
                raise RuntimeError(
                    "未配置 LLM provider：请通过请求 llm 对象传入调用方模型绑定（BYOK，引擎不再使用服务端 key 兜底）"
                )
            self._local.llm_caller = LLMCaller(provider)
            _bound_caller = True
            description_prompt = (
                "You are an image analysis expert. Describe this image in detail "
                "including: subject, setting, colors, lighting, composition, style, "
                "mood, and any notable details. Be comprehensive."
            )
            raw_desc, tokens_desc = self._call_vision_llm(
                description_prompt, request.image_url, request.detail,
            )

            # 加载策略生成平台格式化提示词
            strategy_cls = get_strategy(request.platform.value)
            if not strategy_cls:
                strategy_cls = get_strategy("generic")

            platform_prompt = strategy_cls.build_system_prompt(
                style=request.style,
                creative_level=7,
                max_length=800,
            )
            platform_prompt += (
                "\n\nIMPORTANT: Based on the following image description, "
                "create a high-quality prompt that would regenerate this image."
            )

            msgs = [
                {"role": "system", "content": platform_prompt},
                {"role": "user", "content": raw_desc},
            ]
            optimized, tokens_opt = self._call_llm(platform_prompt, raw_desc)
            final = strategy_cls.post_process(optimized, creative_level=7)

            elapsed = (time.time() - start_time) * 1000
            return ReverseResult(
                prompt=final,
                platform=request.platform,
                style=request.style,
                model_used=provider.model_name,
                description=raw_desc,
                duration_ms=round(elapsed, 1),
                key_source="caller",
                caller=_request_caller(request),
            )
        except Exception as e:
            elapsed = (time.time() - start_time) * 1000
            logger.error("reverse_engineer failed: %s", e)
            return ReverseResult(
                prompt="",
                platform=request.platform,
                style=request.style,
                model_used=provider.model_name if provider is not None else "",
                duration_ms=round(elapsed, 1),
                key_source="caller" if provider is not None else "none",
                caller=_request_caller(request),
                error=str(e),
            )
        finally:
            if _bound_caller:
                try:
                    delattr(self._local, "llm_caller")
                except AttributeError:
                    pass

    def _call_llm_with_timeout(
        self,
        request: OptimizeRequest,
        provider: Optional[BaseLLMProvider] = None,
        provider_id: str = "",
        timeout_seconds: float = 15,
    ) -> OptimizeResult:
        """带超时的 LLM 调用（用于 A/B 并行优化）"""
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(self._do_optimize_sync, request, provider, provider_id)
            try:
                return future.result(timeout=timeout_seconds)
            except concurrent.futures.TimeoutError:
                return OptimizeResult(
                    optimized_prompt=request.prompt,
                    platform=request.platform,
                    error=f"LLM call timeout after {timeout_seconds}s",
                    duration_ms=timeout_seconds * 1000,
                )

    def _do_optimize_sync(
        self,
        request: OptimizeRequest,
        provider: Optional[BaseLLMProvider] = None,
        provider_id: str = "",
    ) -> OptimizeResult:
        """同步执行优化（供 _call_llm_with_timeout 调用）"""
        return self.optimize(request, provider=provider, provider_id=provider_id)
