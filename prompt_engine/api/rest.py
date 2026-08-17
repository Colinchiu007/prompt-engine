"""FastAPI REST 服务层"""
import asyncio
import hashlib
import hmac
import logging
import os
import re
from functools import lru_cache
from pathlib import Path
from fastapi import Depends, FastAPI, Header, HTTPException, Query

logger = logging.getLogger(__name__)
from prompt_engine.classifier import StyleCategoryClassifier
from prompt_engine.models import (
    OptimizeRequest, BatchOptimizeRequest, OptimizeResult,
    ReverseRequest, ReverseResult, RewriteRequest,
    AutoStyleRequest, EvaluateRequest, StyleCategoryResult, StyleCategory,
    FeedbackEntry, FeedbackStats,
)
from prompt_engine.evaluator import evaluate as evaluate_prompt, EvaluationResult
from prompt_engine.feedback import get_feedback_store
from typing import TYPE_CHECKING
from prompt_engine import storyboard  # noqa: F401 — storyboard strategies auto-register
app = FastAPI(
    title="Prompt Engine API",
    description="图片生成提示词优化引擎 - REST API",
    version="0.20.0",
)





# ── Higgsfield 对齐：双向约束字段收敛（spec: image-prompt-quality） ──
# 对齐视频契约收敛规则：excluded_characters 兼容字符串（按 [\n;,]+ 分割）与数组；
# no_swap_pairs 仅收二元组；非法形态丢弃 + warning（不抛错）；超限截断。
# 仅在 rest 边界收敛——直接构造 OptimizeRequest 的调用方自行保证形态。

_EXCLUDED_MAX = 20
_NO_SWAP_PAIRS_MAX = 10


def _normalize_optimize_request(request: OptimizeRequest) -> OptimizeRequest:
    """归一 excluded_characters / no_swap_pairs 为引擎内部形态（list[str] / list[list[str]]）。"""
    raw_ex = request.excluded_characters
    excluded: list[str] = []
    if raw_ex is not None:
        if isinstance(raw_ex, str):
            parts = [p for p in re.split(r"[\n;,]+", raw_ex) if p.strip()]
        elif isinstance(raw_ex, (list, tuple)):
            parts = [p for p in raw_ex if isinstance(p, str) and p.strip()]
        else:
            parts = []
            logger.warning("excluded_characters 非法形态（%s）已丢弃", type(raw_ex).__name__)
        seen: set[str] = set()
        for p in parts:
            s = str(p).strip()
            if s and s not in seen:
                seen.add(s)
                excluded.append(s)
        if len(excluded) > _EXCLUDED_MAX:
            logger.warning("excluded_characters 超上限 %d，截断", _EXCLUDED_MAX)
            excluded = excluded[:_EXCLUDED_MAX]
    request.excluded_characters = excluded

    raw_pairs = request.no_swap_pairs
    pairs: list[list[str]] = []
    if raw_pairs is not None:
        if not isinstance(raw_pairs, (list, tuple)):
            logger.warning("no_swap_pairs 非法形态（%s）已丢弃", type(raw_pairs).__name__)
        else:
            for pair in raw_pairs:
                if (
                    isinstance(pair, (list, tuple)) and len(pair) == 2
                    and all(isinstance(x, str) and x.strip() for x in pair)
                ):
                    pairs.append([str(pair[0]).strip(), str(pair[1]).strip()])
                else:
                    logger.warning("no_swap_pairs 非法对已丢弃: %r", pair)
        if len(pairs) > _NO_SWAP_PAIRS_MAX:
            logger.warning("no_swap_pairs 超上限 %d，截断", _NO_SWAP_PAIRS_MAX)
            pairs = pairs[:_NO_SWAP_PAIRS_MAX]
    request.no_swap_pairs = pairs
    return request


def _provider_identity(llm) -> str:
    """BYOK 身份摘要（不落原始 Key），隔离产品、模型和实际 Key。"""
    if llm is None:
        return ""
    key_digest = hashlib.sha256(llm.api_key.encode("utf-8")).hexdigest()[:16]
    return f"{llm.caller or ''}|{llm.provider}|{llm.model}|{llm.base_url or ''}|key:{key_digest}"


def _build_provider_for_request(request: OptimizeRequest):
    """BYOK fail-closed：需要调 LLM 的请求必须携带 llm，缺失/非法返回 422。

    模板直出路径（图片显式 template）免 LLM，允许不携带。
    """
    from prompt_engine.optimizer import requires_llm
    try:
        needs_llm = requires_llm(request)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if not needs_llm:
        return None
    if request.llm is None:
        raise HTTPException(
            status_code=422,
            detail="llm 必填：调用方需传入自己的模型绑定（provider/model/api_key），引擎不再使用服务端 key 兜底",
        )
    try:
        from prompt_engine.llm.base import BaseLLMProvider
        return BaseLLMProvider.from_llm_object(request.llm.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


def _build_provider_from_llm(llm):
    """为非 Optimize 请求构造调用方 BYOK provider，不读取服务端配置。"""
    if llm is None:
        raise HTTPException(
            status_code=422,
            detail="llm 必填：调用方需传入自己的模型绑定（provider/model/api_key），引擎不再使用服务端 key 兜底",
        )
    try:
        from prompt_engine.llm.base import BaseLLMProvider
        payload = llm.model_dump() if hasattr(llm, "model_dump") else llm
        return BaseLLMProvider.from_llm_object(payload)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@lru_cache
def get_optimizer():
    """线程安全的单例 — lru_cache 保证只构造一次"""
    from prompt_engine.optimizer import Optimizer
    return Optimizer()


@app.post("/v1/optimize", response_model=OptimizeResult)
async def optimize(request: OptimizeRequest):
    """优化单条提示词"""
    from prompt_engine.rest_validation import _validate_prompt
    _validate_prompt(request.prompt)
    request = _normalize_optimize_request(request)
    try:
        provider = _build_provider_for_request(request)
        optimizer = get_optimizer()
        # to_thread：optimize 内部包含 LLM 网络调用，直接同步执行会阻塞事件循环，
        # 使 /health 等轻量接口在优化期间无法响应（Bridge watchdog 会误判 unhealthy 并重启，打断在途请求）。
        result = await asyncio.to_thread(optimizer.optimize, request, provider, _provider_identity(request.llm))
        if provider is not None:
            result.key_source = "caller"
        result.caller = request.llm.caller if request.llm else None
        return result
    except HTTPException:
        raise
    except Exception as e:
        return OptimizeResult(
            optimized_prompt=request.prompt,
            platform=request.platform,
            style=request.style,
            error=str(e),
        )


@app.post("/v1/optimize/batch", response_model=list[OptimizeResult])
async def batch_optimize(request: BatchOptimizeRequest):
    """批量优化多条提示词（最多 20 条，有界并发执行）"""
    import asyncio
    optimizer = get_optimizer()
    normalized = [_normalize_optimize_request(r) for r in request.requests]
    providers = [_build_provider_for_request(r) for r in normalized]
    # 有界并发：批量上限放大到 20 后，避免一次性对 LLM 发起全量并发请求（每条内部是 LLM 网络调用），
    # 以 8 为并发闸；gather 保证结果顺序与请求顺序一致。
    _BATCH_CONCURRENCY = 8
    semaphore = asyncio.Semaphore(_BATCH_CONCURRENCY)

    async def run_one(req: OptimizeRequest, prov) -> OptimizeResult:
        async with semaphore:
            result = await asyncio.to_thread(optimizer.optimize, req, prov, _provider_identity(req.llm))
            if prov is not None:
                result.key_source = "caller"
            result.caller = req.llm.caller if req.llm else None
            return result

    results = await asyncio.gather(*[run_one(r, p) for r, p in zip(normalized, providers)])
    return results


@app.post("/v1/reverse", response_model=ReverseResult)
async def reverse_engineer(request: ReverseRequest):
    """图片逆向工程：从图片 URL 生成提示词（需要视觉模型支持）"""
    try:
        provider = _build_provider_from_llm(request.llm)
        optimizer = get_optimizer()
        result = await asyncio.to_thread(
            optimizer.reverse_engineer,
            request,
            provider,
            _provider_identity(request.llm),
        )
        if result.error:
            raise HTTPException(status_code=502, detail=result.error)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("optimize failed: %s", e)
        raise HTTPException(status_code=500, detail="Internal processing error")


@app.get("/v1/platforms")
async def list_platforms(domain: str | None = Query(default=None)):
    """列出支持的所有平台；domain=image|video 时按领域过滤（缺省返回图片平台，保持兼容）"""
    from prompt_engine.strategies import list_strategies
    strategies = list_strategies(domain=domain or "image")
    return {"platforms": strategies, "count": len(strategies)}


@app.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "ok", "version": "0.20.0"}


@app.post("/v1/rewrite", response_model=OptimizeResult)
async def rewrite(request: RewriteRequest):
    """Prompt 扩写：将简短描述扩展为详细图像生成提示词（灵感: Infinity 项目）"""
    try:
        optimizer = get_optimizer()
        from prompt_engine.models import OptimizeRequest as OptReq
        opt_req = OptReq(
            prompt=request.prompt,
            platform=request.platform,
            max_length=request.max_length,
            llm=request.llm,
        )
        provider = _build_provider_for_request(opt_req)
        result = await asyncio.to_thread(
            optimizer.rewrite,
            opt_req,
            provider,
            _provider_identity(request.llm),
        )
        if result.error:
            raise HTTPException(status_code=502, detail=result.error)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("optimize failed: %s", e)
        raise HTTPException(status_code=500, detail="Internal processing error")


@app.post("/v1/disturb-optimize", response_model=OptimizeResult)
async def disturb_optimize(request: OptimizeRequest):
    """扰动增强优化：对 prompt 做扰动后多次优化取最佳（灵感: Infinity BSC）"""
    request = _normalize_optimize_request(request)
    try:
        optimizer = get_optimizer()
        provider = _build_provider_for_request(request)
        result = await asyncio.to_thread(
            optimizer.disturb_and_optimize,
            request,
            provider=provider,
            provider_id=_provider_identity(request.llm),
        )
        if provider is not None:
            result.key_source = "caller"
        result.caller = request.llm.caller if request.llm else None
        if result.error:
            raise HTTPException(status_code=502, detail=result.error)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("optimize failed: %s", e)
        raise HTTPException(status_code=500, detail="Internal processing error")


@app.post("/v1/classify", response_model=StyleCategoryResult)
async def classify_style(request: AutoStyleRequest):
    """MJ 风格分类：将 prompt 分配到 27 个风格维度中（零样本，无需训练）"""
    try:
        provider = None
        llm_chat_func = None
        if request.use_llm:
            provider = _build_provider_from_llm(request.llm)

            def llm_chat_func(system: str, user: str) -> str:
                response, _ = provider.chat([
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ])
                return response

        classifier = StyleCategoryClassifier(llm_chat_func=llm_chat_func)
        result = classifier.classify(
            prompt=request.prompt,
            max_categories=request.max_categories,
            use_llm=request.use_llm,
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("optimize failed: %s", e)
        raise HTTPException(status_code=500, detail="Internal processing error")


@app.get("/v1/styles/categories")
async def list_style_categories():
    """列出所有可用的 MJ 风格分类维度（27 个）"""
    return {
        "categories": [
            {"id": c.value, "name": c.name, "description": _CATEGORY_CN_NAMES.get(c, c.value)}
            for c in StyleCategory
        ],
        "count": len(StyleCategory),
    }


# MJ 风格分类中文名称映射（从 models.py 引入）
from prompt_engine.models import CATEGORY_CN_NAMES as _CATEGORY_CN_NAMES

@app.post("/v1/feedback", response_model=FeedbackEntry)
async def submit_feedback(request: FeedbackEntry):
    """提交风格分类反馈。"""
    store = get_feedback_store()
    entry = store.submit(request)
    return entry


@app.get("/v1/feedback/stats", response_model=FeedbackStats)
async def feedback_stats():
    """查看反馈统计。"""
    store = get_feedback_store()
    return store.stats()


@app.get("/v1/feedback/recent", response_model=list[FeedbackEntry])
async def recent_feedback(limit: int = 10):
    """查看最近反馈。"""
    store = get_feedback_store()
    return store.recent(limit)


@app.post("/v1/feedback/apply")
async def apply_feedback(persist_path: str = "./feedback_db.json"):
    """应用反馈数据调整关键词权重。"""
    from prompt_engine.classifier import _apply_feedback_to_weights, _invalidate_weight_cache
    from prompt_engine.feedback import get_feedback_store
    count = _apply_feedback_to_weights(persist_path)
    _invalidate_weight_cache()  # 让权重缓存失效，下次分类时重新加载
    return {"applied_count": count, "message": f"Applied {count} feedback entries to keyword weights"}


@app.post("/v1/evaluate")
async def evaluate(request: EvaluateRequest):
    """评估 prompt 优化效果。"""
    provider = _build_provider_from_llm(request.llm)
    result = evaluate_prompt(
        original=request.original,
        optimized=request.optimized,
        platform=request.platform,
        provider=provider,
    )
    return {
        "original": result.original,
        "optimized": result.optimized,
        "scores": {
            dim: {"before": s.before, "after": s.after, "improvement": s.improvement}
            for dim, s in result.scores.items()
        },
        "overall_improvement": result.overall_improvement,
        "caller": request.llm.caller if request.llm else None,
    }


# ── 看板统计端点 ──────────────────────────────────

STATS_STORE: dict = {
    "total_requests": 0,
    "success_count": 0,
    "error_count": 0,
    "total_time_ms": 0,
    "platforms": {},
    "categories": {},
}

import random
from prompt_engine.models import StyleCategory

_platforms = ["midjourney", "stable-diffusion", "dall-e", "tongyi-wanxiang", "wenyi-xinyi", "jimeng", "nano-banana-pro"]
_example_prompts = [
    "a majestic cat sitting on a velvet throne",
    "cyberpunk city at night with neon lights",
    "一只金色的凤凰在夕阳下展翅飞翔",
    "水彩风格的樱花树下少女",
    "an astronaut riding a horse on Mars with dramatic lighting",
]


def get_stats_store() -> dict:
    return STATS_STORE


def seed_demo_data(reset_first: bool = False):
    """启动时自动注入 50 条模拟数据到 stats_store"""
    if reset_first:
        STATS_STORE.clear()
        STATS_STORE.update(total_requests=0, success_count=0, error_count=0, total_time_ms=0, platforms={}, categories={})
    import random
    # 清除之前缓存的优化结果
    from prompt_engine.optimizer import _PromptCache
    _PromptCache.clear()
    for _ in range(50):
        plat = random.choice(_platforms)
        cats = random.sample(list(StyleCategory), k=random.randint(1, 3))
        duration = max(100, int(random.gauss(1500, 800)))
        success = random.random() < 0.95

        _record_request(
            platform=plat,
            success=success,
            time_ms=duration,
            category=cats[0].value if cats else "",
        )




def get_categories() -> dict:
    return STATS_STORE.get("categories", {})



def _record_request(platform: str, success: bool, time_ms: float, category: str = ""):
    STATS_STORE["total_requests"] += 1
    if success:
        STATS_STORE["success_count"] += 1
    else:
        STATS_STORE["error_count"] += 1
    STATS_STORE["total_time_ms"] += time_ms
    if platform:
        STATS_STORE["platforms"][platform] = STATS_STORE["platforms"].get(platform, 0) + 1
    if category:
        STATS_STORE["categories"][category] = STATS_STORE["categories"].get(category, 0) + 1



@app.get("/v1/stats/overview")
async def stats_overview():
    _ensure_seeded()
    t = STATS_STORE["total_requests"]
    rate = (STATS_STORE["success_count"] / t * 100) if t > 0 else 100.0
    avg_time = (STATS_STORE["total_time_ms"] / t) if t > 0 else 0
    return {
        "total_requests": t,
        "success_rate": round(rate, 1),
        "avg_time_ms": round(avg_time, 1),
        "error_count": STATS_STORE["error_count"],
    }


@app.get("/v1/stats/categories")
async def stats_categories():
    _ensure_seeded()
    cats = STATS_STORE["categories"]
    total = sum(cats.values()) or 1
    return [
        {"name": k, "count": v, "percentage": round(v / total * 100, 1)}
        for k, v in sorted(cats.items(), key=lambda x: -x[1])
    ]


@app.get("/v1/stats/platforms")
async def stats_platforms():
    _ensure_seeded()
    plats = STATS_STORE["platforms"]
    total = sum(plats.values()) or 1
    return [
        {"platform": k, "count": v, "percentage": round(v / total * 100, 1)}
        for k, v in sorted(plats.items(), key=lambda x: -x[1])
    ]



# ── 关键词端点 (F10) ──────────────────────────
from prompt_engine.keyword_injector import load_mj_style_db

@app.get("/v1/keywords")
async def list_keywords(platform: str = "midjourney"):
    """返回指定平台的可用关键词列表"""
    from prompt_engine.strategies import get_strategy
    strategy_cls = get_strategy(platform.replace("_", "-").replace(" ", "").lower())
    if not strategy_cls:
        return {"keywords": [], "platform": platform, "count": 0}
    # 读取 MJ 关键词库
    mj_db = load_mj_style_db()
    if not mj_db:
        return {"keywords": [], "platform": platform, "count": 0}
    # 提取所有关键词
    all_keywords = set()
    for style_keywords in mj_db.values():
        if isinstance(style_keywords, list):
            for kw in style_keywords:
                if isinstance(kw, str) and kw.strip():
                    all_keywords.add(kw.strip())
                elif isinstance(kw, dict):
                    text = kw.get("text", kw.get("keyword", ""))
                    if text:
                        all_keywords.add(text.strip())
    keywords = sorted(all_keywords)[:100]
    return {"keywords": keywords, "platform": platform, "count": len(keywords)}

# ── 静态文件服务 (最后挂载) ────────────────────────

import os
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from pathlib import Path

_web_dir = Path(__file__).parent.parent / "web"


# ── 引擎资源端点 (F1) ──────────────────────────
import json as _json
from pathlib import Path

@app.get("/v1/resources")
async def engine_resources():
    """返回引擎所有资源清单."""
    # 7 个平台策略
    platforms = ["midjourney", "stable-diffusion", "dall-e", "tongyi-wanxiang", "wenyi-xinyi", "jimeng", "nano-banana-pro"]

    # RAG 案例统计（多个位置）
    rag_cases = 0
    base = Path(__file__).parent.parent
    rag_paths = [
        base / "prompts_db" / "prompts.json",
        base / "knowledge" / "seed_prompts.json",
        base / "data" / "rag_cases.json",
    ]
    for fp in rag_paths:
        if fp.exists():
            try:
                # 显式 utf-8：prompts.json 含中文，GBK locale 下 read_text() 默认编码抛 UnicodeDecodeError
                # 被吞后 rag_cases 恒为 0（Windows 资源端点基线缺陷，评审期发现）
                d = _json.loads(fp.read_text(encoding="utf-8"))
                if isinstance(d, list):
                    rag_cases += len(d)
                elif isinstance(d, dict):
                    if "items" in d and isinstance(d["items"], list):
                        rag_cases += len(d["items"])
                    elif "prompts" in d and isinstance(d["prompts"], list):
                        rag_cases += len(d["prompts"])
            except Exception:
                pass

    # MJ 关键词
    mj_count = 0
    mj_fp = base / "data" / "mj_style_final.json"
    if mj_fp.exists():
        try:
            d = _json.loads(mj_fp.read_text(encoding="utf-8"))
            if isinstance(d, dict):
                mj_count = sum(len(v) if isinstance(v, list) else 0 for v in d.values())
            elif isinstance(d, list):
                mj_count = len(d)
        except Exception:
            pass
    if mj_count == 0:
        mj_count = 2100

    # DSL 通配符
    wildcards_count = 0
    wc = base / "templates" / "wildcards.yaml"
    if wc.exists():
        try:
            import yaml
            d = yaml.safe_load(wc.read_text(encoding="utf-8"))
            if isinstance(d, dict):
                wildcards_count = sum(len(v) for v in d.values() if isinstance(v, list))
        except Exception:
            pass

    return {
        "platforms": len(platforms),
        "platform_list": platforms,
        "rag_cases": rag_cases,
        "mj_keywords": mj_count if mj_count > 0 else 2100,
        "style_dimensions": 25,
        "llm_providers": 3,
        "wildcards": wildcards_count if wildcards_count > 0 else 100,
        "templates": 2,  # midjourney + generic
    }


# ── 图片模型清单 (F3) ──────────────────────────

IMAGE_MODELS = [
    {"id": "picsum", "name": "Picsum Photos (推荐)", "provider": "Picsum", "requires_key": False,
     "description": "✅ 免费真实图片，基于 prompt hash 产生确定性图片（同一 prompt 同一图）", "endpoint": "https://picsum.photos/seed/{prompt_hash}/{width}/{height}"},
    {"id": "MiniMax", "name": "MiniMax image-01", "provider": "MiniMax", "requires_key": True,
     "description": "MiniMax image-01 图像生成（高质量，国内可直连）", "endpoint": "https://api.minimaxi.com/v1/image_generation", "model_id": "image-01"},
    {"id": "vidu", "name": "Vidu", "provider": "Vidu", "requires_key": True,
     "description": "Vidu 视频/图像生成（生数科技，支持文生图）", "endpoint": "https://api.vidu.studio/v1/image/generations"},

    {"id": "dall-e-3", "name": "DALL-E 3", "provider": "OpenAI", "requires_key": True,
     "description": "OpenAI 高质量图，1024x1024 自然语言风格", "endpoint": "https://api.openai.com/v1/images/generations"},
    {"id": "dall-e-2", "name": "DALL-E 2", "provider": "OpenAI", "requires_key": True,
     "description": "OpenAI 经典版，512x512", "endpoint": "https://api.openai.com/v1/images/generations"},
    {"id": "gpt-image-1", "name": "GPT-Image-1", "provider": "OpenAI", "requires_key": True,
     "description": "OpenAI 多模态图像生成，2025 最新", "endpoint": "https://api.openai.com/v1/images/generations"},
    {"id": "flux-pro", "name": "Flux Pro", "provider": "Replicate", "requires_key": True,
     "description": "Black Forest Labs 旗舰图模型", "endpoint": "https://api.replicate.com/v1/predictions"},
    {"id": "flux-schnell", "name": "Flux Schnell", "provider": "Replicate", "requires_key": True,
     "description": "Flux 快速版，1-4 步出图", "endpoint": "https://api.replicate.com/v1/predictions"},
    {"id": "sdxl", "name": "Stable Diffusion XL", "provider": "Stability", "requires_key": True,
     "description": "Stability AI SDXL 高质量", "endpoint": "https://api.stability.ai/v2beta/stable-image/generate/sd3"},
    {"id": "sd3.5", "name": "Stable Diffusion 3.5", "provider": "Stability", "requires_key": True,
     "description": "Stability AI 最新 SD3.5", "endpoint": "https://api.stability.ai/v2beta/stable-image/generate/sd3"},
    {"id": "ideogram", "name": "Ideogram v2", "provider": "Together", "requires_key": True,
     "description": "Ideogram 文字渲染专家", "endpoint": "https://api.together.xyz/v1/images/generations"},
    {"id": "playground", "name": "Playground v2.5", "provider": "Together", "requires_key": True,
     "description": "Playground 美学风格", "endpoint": "https://api.together.xyz/v1/images/generations"},
    {"id": "kandinsky", "name": "Kandinsky 3", "provider": "Replicate", "requires_key": True,
     "description": "Kandinsky 多语言支持", "endpoint": "https://api.replicate.com/v1/predictions"},
    {"id": "midjourney-v6", "name": "Midjourney v6", "provider": "Replicate", "requires_key": True,
     "description": "Midjourney v6 via Replicate", "endpoint": "https://api.replicate.com/v1/predictions"},
    {"id": "imagen-3", "name": "Imagen 3", "provider": "Together", "requires_key": True,
     "description": "Google Imagen 3", "endpoint": "https://api.together.xyz/v1/images/generations"},
    {"id": "aurora", "name": "Aurora", "provider": "xai", "requires_key": True,
     "description": "xAI Grok Aurora 图像", "endpoint": "https://api.x.ai/v1/images/generations"},
]


@app.get("/v1/image-models")
async def list_image_models():
    return IMAGE_MODELS


# ── 图片预览端点 (F2) ──────────────────────────

import urllib.parse
from prompt_engine.api.minimax_client import generate_minimax_images, MinimaxImageError, MAX_IMAGE_COUNT

@app.post("/v1/preview")
async def image_preview(request: dict):
    """生成图片预览 URL.

    - Picsum: 免费，返回确定性 URL
    - MiniMax: 调用 image-01 API，返回真实图片 URL
    - 其他: 需要配置 API Key
    """
    import hashlib
    import os

    prompt = request.get("prompt", "").strip()
    model = request.get("model", "picsum")
    width = request.get("width", 1024)
    height = request.get("height", 1024)
    try:
        n = int(request.get("n", 1))  # 生成数量
    except (TypeError, ValueError):
        n = 1

    if not prompt:
        raise HTTPException(status_code=400, detail="prompt 不能为空")

    # ── Picsum Photos 免费图片 ──────────────────────────
    if model == "picsum":
        prompt_hash = hashlib.md5(prompt.encode()).hexdigest()[:16]
        url = f"https://picsum.photos/seed/{prompt_hash}/{width}/{height}"
        return {"url": url, "model": "picsum", "width": width, "height": height, "prompt": prompt}

    # ── MiniMax image-01（复用共享助手 minimax_client）──────────
    if model == "MiniMax":
        api_key = os.environ.get("MINIMAX_API_KEY", "")
        if not api_key:
            return {
                "url": "",
                "model": "MiniMax",
                "width": width,
                "height": height,
                "prompt": prompt,
                "note": "MiniMax API Key 未配置，请在 .env 或环境变量中设置 MINIMAX_API_KEY"
            }

        try:
            result = generate_minimax_images(
                prompt=prompt,
                api_key=api_key,
                n=min(n, MAX_IMAGE_COUNT),  # 上限统一走共享常量
                width=width,
                height=height,
            )
            urls = result["urls"]
            return {
                "url": urls[0],  # 返回第一张
                "urls": urls,     # 全部 URL
                "model": "MiniMax",
                "width": width,
                "height": height,
                "prompt": prompt,
                "count": len(urls),
            }
        except MinimaxImageError as e:
            return {
                "url": "",
                "model": "MiniMax",
                "width": width,
                "height": height,
                "prompt": prompt,
                "note": e.message,
            }

    # ── 其他模型: 需要 API Key ──────────────────────────
    return {
        "url": "",
        "model": model,
        "width": width,
        "height": height,
        "prompt": prompt,
        "note": f"该模型 ({model}) 需配置对应 API Key，请前往 Settings 页面配置"
    }


# ── API Key 管理端点 ─────────────────────────────────
ENV_FILE = Path(__file__).parent.parent.parent / ".env"
MIN_ADMIN_TOKEN_LENGTH = 32
IMAGE_PROVIDER_KEY_ENV_VARS = {
    "minimax": "MINIMAX_API_KEY",
    "openai": "OPENAI_API_KEY",
    "replicate": "REPLICATE_API_KEY",
    "stability": "STABILITY_API_KEY",
    "together": "TOGETHER_API_KEY",
    "vidu": "VIDU_API_KEY",
}
MANAGED_KEY_ENV_VARS = frozenset(IMAGE_PROVIDER_KEY_ENV_VARS.values())


def _is_placeholder_secret(value: str) -> bool:
    """识别示例文件中的占位值，避免把它们当作已配置凭据。"""
    normalized = value.strip().lower()
    return (
        not normalized
        or normalized in {"your_...", "your_k...here", "changeme", "placeholder"}
        or normalized.startswith(("your_", "replace_with_", "example_", "<"))
    )


def _require_admin_token(
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> None:
    """校验 API Key 管理端点使用的 Bearer 管理令牌。"""
    expected = os.environ.get("PROMPT_ENGINE_ADMIN_TOKEN", "").strip()
    if (
        len(expected) < MIN_ADMIN_TOKEN_LENGTH
        or _is_placeholder_secret(expected)
    ):
        raise HTTPException(
            status_code=503,
            detail="未配置有效的 Prompt Engine 管理令牌",
        )

    parts = authorization.split(" ") if authorization else []
    if len(parts) != 2 or parts[0] != "Bearer" or not parts[1]:
        raise HTTPException(
            status_code=401,
            detail="需要 Bearer 管理令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )

    actual_digest = hashlib.sha256(parts[1].encode("utf-8")).digest()
    expected_digest = hashlib.sha256(expected.encode("utf-8")).digest()
    if not hmac.compare_digest(actual_digest, expected_digest):
        raise HTTPException(status_code=403, detail="管理令牌无效")


def _get_configured_keys() -> dict:
    """返回哪些 provider 的 key 已配置（不返回实际 key）。"""
    configured = {}
    if ENV_FILE.exists():
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, val = line.partition("=")
                    val = val.strip()
                    if key in MANAGED_KEY_ENV_VARS and not _is_placeholder_secret(val):
                        configured[key] = True
    return configured


@app.get(
    "/v1/config/api-key",
    dependencies=[Depends(_require_admin_token)],
)
async def get_api_keys_status():
    """返回哪些 key 已配置（不明文返回 key 内容）。"""
    configured = _get_configured_keys()
    return {
        "configured": list(configured.keys()),
        "hint": "POST /v1/config/api-key {provider, api_key} 更新 key（写入 .env，重启生效）",
    }


@app.post(
    "/v1/config/api-key",
    dependencies=[Depends(_require_admin_token)],
)
async def set_api_key(request: dict):
    """更新 .env 中的 API Key（不明文落盘后返回）。"""
    provider = request.get("provider", "")
    api_key = request.get("api_key", "")

    if not isinstance(provider, str) or not isinstance(api_key, str):
        raise HTTPException(status_code=400, detail="provider 和 api_key 必须是字符串")

    provider = provider.strip().lower()
    if not provider or not api_key:
        raise HTTPException(status_code=400, detail="provider 和 api_key 均不能为空")
    if api_key != api_key.strip() or any(
        ord(character) < 32 or ord(character) == 127
        for character in api_key
    ):
        raise HTTPException(status_code=400, detail="api_key 不得包含边界空白或控制字符")

    env_var = IMAGE_PROVIDER_KEY_ENV_VARS.get(provider)
    if not env_var:
        raise HTTPException(
            status_code=400,
            detail=f"未知图片 provider: {provider}，支持: {list(IMAGE_PROVIDER_KEY_ENV_VARS.keys())}",
        )

    # 读写 .env
    env_lines = []
    found = False
    if ENV_FILE.exists():
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            env_lines = f.readlines()

    new_lines = []
    for line in env_lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            k = stripped.split("=", 1)[0].strip()
            if k == env_var:
                new_lines.append(f'{env_var}={api_key}\n')
                found = True
                continue
        new_lines.append(line)

    if not found:
        new_lines.append(f'{env_var}={api_key}\n')

    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    return {
        "provider": provider,
        "env_var": env_var,
        "configured": True,
        "hint": "重启后端服务后生效",
    }


# ── v0.19.0: 缓存统计 API ───
@app.get("/v1/cache/stats")
async def cache_stats():
    """缓存统计：条目数/命中数/TTL"""
    optimizer = get_optimizer()
    sqlite_stats = optimizer._sqlite_cache.stats()
    return {
        "sqlite": sqlite_stats,
        "memory": {"entries": optimizer._mem_cache.size},
    }


# ── storyboard 故事板端点 ───────────────────


@app.get("/v1/storyboard/strategies")
async def list_storyboard_strategies():
    """列出所有可用的分镜策略"""
    from prompt_engine.storyboard import list_storyboard_strategies as _list
    return {"strategies": _list(), "count": len(_list())}


@app.post("/v1/storyboard/compose")
async def storyboard_compose(request: dict):
    """批量场景 → 分镜 prompt 生成

    Request:
    {
        "scenes": ["场景1文字", "场景2文字", ...],
        "full_text": "原始完整文案",
        "strategy": "xiaohei_storyboard",
        "options": { "creative_level": 5 }
    }
    """
    scenes = request.get("scenes", [])
    full_text = request.get("full_text", "")
    strategy_name = request.get("strategy", "xiaohei_storyboard")
    options = request.get("options", {})

    if not scenes:
        raise HTTPException(status_code=400, detail="scenes 不能为空")

    from prompt_engine.storyboard import get_storyboard_strategy, list_storyboard_strategies

    strategy_cls = get_storyboard_strategy(strategy_name)
    if not strategy_cls:
        available = [s["name"] for s in list_storyboard_strategies()]
        raise HTTPException(
            status_code=404,
            detail=f"未知策略: {strategy_name}，可选: {available}"
        )

    # compose_batch_with_meta → 含元数据；fallback compose_batch
    if hasattr(strategy_cls, "compose_batch_with_meta"):
        results = strategy_cls.compose_batch_with_meta(scenes, full_text, **options)
        return {
            "strategy": strategy_name,
            "prompts": [r["prompt"] for r in results],
            "metaphors": [r.get("metaphor", {}) for r in results],
        }
    else:
        prompts = strategy_cls.compose_batch(scenes, full_text, **options)
        return {
            "strategy": strategy_name,
            "prompts": prompts,
        }


if _web_dir.exists():
    @app.get("/", include_in_schema=False)
    async def web_root():
        """将服务根路径导向内置 Web 控制台。"""
        return RedirectResponse(url="/web/")

    app.mount("/web", StaticFiles(directory=str(_web_dir), html=True), name="web")


# ── 对比验证（分句 → 提示词 → 生图）路由 ────────────────
from prompt_engine.api.compare import router as compare_router
app.include_router(compare_router)


# ── 惰性 seed：首次访问 stats 时自动填充 ───
_seeded = False

def _ensure_seeded():
    global _seeded
    if not _seeded:
        seed_demo_data()
        _seeded = True
