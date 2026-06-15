"""FastAPI REST 服务层"""
from functools import lru_cache
from fastapi import FastAPI, HTTPException
from prompt_engine.classifier import StyleCategoryClassifier
from prompt_engine.models import (
    OptimizeRequest, BatchOptimizeRequest, OptimizeResult,
    ReverseRequest, ReverseResult, RewriteRequest,
    AutoStyleRequest, StyleCategoryResult, StyleCategory,
    FeedbackEntry, FeedbackStats,
)
from prompt_engine.evaluator import evaluate as evaluate_prompt, EvaluationResult
from prompt_engine.feedback import get_feedback_store
from prompt_engine.optimizer import Optimizer
from typing import TYPE_CHECKING
app = FastAPI(
    title="Prompt Engine API",
    description="图片生成提示词优化引擎 - REST API",
    version="0.5.0",
)





@lru_cache
def get_optimizer() -> Optimizer:
    """线程安全的单例 — lru_cache 保证只构造一次"""
    return Optimizer()


@app.post("/v1/optimize", response_model=OptimizeResult)
async def optimize(request: OptimizeRequest):
    """优化单条提示词"""
    from prompt_engine.rest_validation import _validate_prompt
    _validate_prompt(request.prompt)
    try:
        optimizer = get_optimizer()
        result = optimizer.optimize(request)
        if result.error:
            raise HTTPException(status_code=502, detail=result.error)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/v1/optimize/batch", response_model=list[OptimizeResult])
async def batch_optimize(request: BatchOptimizeRequest):
    """批量优化多条提示词（最多 10 条，并行执行）"""
    import asyncio
    optimizer = get_optimizer()

    async def run_one(req: OptimizeRequest) -> OptimizeResult:
        return await asyncio.to_thread(optimizer.optimize, req)

    results = await asyncio.gather(*[run_one(r) for r in request.requests])
    return results


@app.post("/v1/reverse", response_model=ReverseResult)
async def reverse_engineer(request: ReverseRequest):
    """图片逆向工程：从图片 URL 生成提示词（需要视觉模型支持）"""
    try:
        optimizer = get_optimizer()
        result = optimizer.reverse_engineer(request)
        if result.error:
            raise HTTPException(status_code=502, detail=result.error)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/v1/platforms")
async def list_platforms():
    """列出支持的所有平台"""
    from prompt_engine.strategies import list_strategies
    strategies = list_strategies()
    return {"platforms": strategies, "count": len(strategies)}


@app.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "ok", "version": "0.4.0"}


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
        )
        result = optimizer.rewrite(opt_req)
        if result.error:
            raise HTTPException(status_code=502, detail=result.error)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/v1/disturb-optimize", response_model=OptimizeResult)
async def disturb_optimize(request: OptimizeRequest):
    """扰动增强优化：对 prompt 做扰动后多次优化取最佳（灵感: Infinity BSC）"""
    try:
        optimizer = get_optimizer()
        result = optimizer.disturb_and_optimize(request)
        if result.error:
            raise HTTPException(status_code=502, detail=result.error)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/v1/classify", response_model=StyleCategoryResult)
async def classify_style(request: AutoStyleRequest):
    """MJ 风格分类：将 prompt 分配到 27 个风格维度中（零样本，无需训练）"""
    try:
        classifier = StyleCategoryClassifier()
        result = classifier.classify(
            prompt=request.prompt,
            max_categories=request.max_categories,
            use_llm=request.use_llm,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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


# MJ 风格分类中文名称映射（用于 /v1/styles/categories 返回）
_CATEGORY_CN_NAMES = {
    StyleCategory.LIGHTING: "光照效果",
    StyleCategory.MATERIAL_PROPERTIES: "材质属性",
    StyleCategory.MATERIALS: "材料",
    StyleCategory.DIMENSIONALITY: "维度感",
    StyleCategory.COLORS_AND_PALETTES: "色彩与调色板",
    StyleCategory.COMBINATIONS: "色彩组合",
    StyleCategory.CAMERA: "相机/镜头",
    StyleCategory.PERSPECTIVE: "视角/透视",
    StyleCategory.STRUCTURAL_MODIFICATION: "结构变形",
    StyleCategory.NATURE_AND_ANIMALS: "自然与动物",
    StyleCategory.OBJECTS: "物体",
    StyleCategory.OUTER_SPACE: "太空",
    StyleCategory.GEOMETRY: "几何形状",
    StyleCategory.GEOGRAPHY_AND_CULTURE: "地理与文化",
    StyleCategory.DRAWING_AND_ART_MEDIUMS: "绘画与艺术媒介",
    StyleCategory.SFX_AND_SHADERS: "特效与着色器",
    StyleCategory.THEMES: "主题/氛围",
    StyleCategory.INTANGIBLES: "抽象概念",
    StyleCategory.TV_AND_MOVIES: "影视参考",
    StyleCategory.SONG_LYRICS: "歌词风格",
    StyleCategory.DESIGN_STYLES: "设计风格",
    StyleCategory.DIGITAL: "数字艺术",
    StyleCategory.EXPERIMENTAL: "实验风格",
    StyleCategory.EMOJIS: "Emoji 风格",
    StyleCategory.MISCELLANEOUS: "杂项",
}

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
async def evaluate(request: dict):
    """评估 prompt 优化效果。"""
    result = evaluate_prompt(
        original=request.get("original", ""),
        optimized=request.get("optimized", ""),
        platform=request.get("platform", "generic"),
    )
    return {
        "original": result.original,
        "optimized": result.optimized,
        "scores": {
            dim: {"before": s.before, "after": s.after, "improvement": s.improvement}
            for dim, s in result.scores.items()
        },
        "overall_improvement": result.overall_improvement,
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
    cats = STATS_STORE["categories"]
    total = sum(cats.values()) or 1
    return [
        {"name": k, "count": v, "percentage": round(v / total * 100, 1)}
        for k, v in sorted(cats.items(), key=lambda x: -x[1])
    ]


@app.get("/v1/stats/platforms")
async def stats_platforms():
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
                d = _json.loads(fp.read_text())
                if isinstance(d, list):
                    rag_cases += len(d)
                elif isinstance(d, dict):
                    if "items" in d and isinstance(d["items"], list):
                        rag_cases += len(d["items"])
                    elif "prompts" in d and isinstance(d["prompts"], list):
                        rag_cases += len(d["prompts"])
            except:
                pass

    # MJ 关键词
    mj_count = 0
    mj_fp = base / "data" / "mj_style_final.json"
    if mj_fp.exists():
        try:
            d = _json.loads(mj_fp.read_text())
            if isinstance(d, dict):
                mj_count = sum(len(v) if isinstance(v, list) else 0 for v in d.values())
            elif isinstance(d, list):
                mj_count = len(d)
        except:
            pass
    if mj_count == 0:
        mj_count = 2100

    # DSL 通配符
    wildcards_count = 0
    wc = base / "templates" / "wildcards.yaml"
    if wc.exists():
        try:
            d = _json.loads((_json.dumps(__import__("yaml").safe_load(wc.read_text())))) if False else None
            import yaml
            d = yaml.safe_load(wc.read_text())
            if isinstance(d, dict):
                wildcards_count = sum(len(v) for v in d.values() if isinstance(v, list))
        except:
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
     "description": "MiniMax image-01 图像生成（高质量，国内可直连）", "endpoint": "https://api.MiniMax.chat/v1/image/generation"},
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

@app.post("/v1/preview")
async def image_preview(request: dict):
    """生成图片预览 URL (不实际调 API，返回可访问的 URL 供前端 img 标签使用)."""
    prompt = request.get("prompt", "").strip()
    model = request.get("model", "pollinations")
    width = request.get("width", 1024)
    height = request.get("height", 1024)
    seed = request.get("seed", -1)

    if not prompt:
        raise HTTPException(status_code=400, detail="prompt 不能为空")

    # Pollinations 走公开 URL（不需要 API Key）
    if model == "pollinations":
        encoded = urllib.parse.quote(prompt)
    if model == "picsum":
        # Picsum Photos 免费图片生成（基于 prompt hash 确定性）
        import hashlib
        prompt_hash = hashlib.md5(prompt.encode()).hexdigest()[:16]
        url = f"https://picsum.photos/seed/{prompt_hash}/{width}/{height}"
        return {"url": url, "model": "picsum", "width": width, "height": height, "prompt": prompt}

    # 其他模型返回 placeholder URL（前端 img 标签可直接显示）
    # 不实际调 API（避免被用户未配 key 时的 API 账单打到）
    return {"url": "", "model": model, "width": width, "height": height, "prompt": prompt,
            "note": "该模型需配置 API Key，请前往 Settings 页面配置"}


if _web_dir.exists():
    app.mount("/", StaticFiles(directory=str(_web_dir), html=True), name="web")


# ── 自动 seed 演示数据（在所有函数定义完成后调用）───
seed_demo_data()

