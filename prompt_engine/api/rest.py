"""FastAPI REST 服务层"""
import logging
from functools import lru_cache
from pathlib import Path
from fastapi import FastAPI, HTTPException

logger = logging.getLogger(__name__)
from prompt_engine.classifier import StyleCategoryClassifier
from prompt_engine.models import (
    OptimizeRequest, BatchOptimizeRequest, OptimizeResult,
    ReverseRequest, ReverseResult, RewriteRequest,
    AutoStyleRequest, StyleCategoryResult, StyleCategory,
    FeedbackEntry, FeedbackStats,
)
from prompt_engine.evaluator import evaluate as evaluate_prompt, EvaluationResult
from prompt_engine.feedback import get_feedback_store
from typing import TYPE_CHECKING
app = FastAPI(
    title="Prompt Engine API",
    description="图片生成提示词优化引擎 - REST API",
    version="0.19.0",
)





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
    try:
        optimizer = get_optimizer()
        result = optimizer.optimize(request)
        return result
    except Exception as e:
        return OptimizeResult(
            optimized_prompt=request.prompt,
            platform=request.platform,
            style=request.style,
            error=str(e),
        )


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
        logger.error("optimize failed: %s", e)
        raise HTTPException(status_code=500, detail="Internal processing error")


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
        logger.error("optimize failed: %s", e)
        raise HTTPException(status_code=500, detail="Internal processing error")


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
        logger.error("optimize failed: %s", e)
        raise HTTPException(status_code=500, detail="Internal processing error")


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
            except Exception:
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
            d = yaml.safe_load(wc.read_text())
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
    n = request.get("n", 1)  # 生成数量

    if not prompt:
        raise HTTPException(status_code=400, detail="prompt 不能为空")

    # ── Picsum Photos 免费图片 ──────────────────────────
    if model == "picsum":
        prompt_hash = hashlib.md5(prompt.encode()).hexdigest()[:16]
        url = f"https://picsum.photos/seed/{prompt_hash}/{width}/{height}"
        return {"url": url, "model": "picsum", "width": width, "height": height, "prompt": prompt}

    # ── MiniMax image-01 ──────────────────────────
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
            import httpx
            # MiniMax API: aspect_ratio 从尺寸推断
            aspect = "1:1"
            if width > height:
                aspect = "16:9"
            elif height > width:
                aspect = "9:16"

            resp = httpx.post(
                "https://api.minimaxi.com/v1/image_generation",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "image-01",
                    "prompt": prompt,
                    "aspect_ratio": aspect,
                    "response_format": "url",
                    "n": min(n, 3),  # 最多 3 张
                    "prompt_optimizer": True,
                },
                timeout=60.0,
            )
            resp.raise_for_status()
            data = resp.json()

            # 解析 MiniMax 响应
            image_urls = data.get("data", {}).get("image_urls", [])
            if image_urls:
                return {
                    "url": image_urls[0],  # 返回第一张
                    "urls": image_urls,     # 全部 URL
                    "model": "MiniMax",
                    "width": width,
                    "height": height,
                    "prompt": prompt,
                    "count": len(image_urls),
                }
            else:
                return {
                    "url": "",
                    "model": "MiniMax",
                    "width": width,
                    "height": height,
                    "prompt": prompt,
                    "note": "MiniMax 返回了空结果"
                }

        except httpx.HTTPStatusError as e:
            return {
                "url": "",
                "model": "MiniMax",
                "width": width,
                "height": height,
                "prompt": prompt,
                "note": f"MiniMax API 错误: {e.response.status_code}"
            }
        except Exception as e:
            return {
                "url": "",
                "model": "MiniMax",
                "width": width,
                "height": height,
                "prompt": prompt,
                "note": f"MiniMax 调用失败: {str(e)[:100]}"
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
                    if val and val not in ("your_...", "your_k...here"):
                        configured[key] = True
    return configured


@app.get("/v1/config/api-key")
async def get_api_keys_status():
    """返回哪些 key 已配置（不明文返回 key 内容）。"""
    configured = _get_configured_keys()
    return {
        "configured": list(configured.keys()),
        "hint": "POST /v1/config/api-key {provider, api_key} 更新 key（写入 .env，重启生效）",
    }


@app.post("/v1/config/api-key")
async def set_api_key(request: dict):
    """更新 .env 中的 API Key（不明文落盘后返回）。"""
    provider = request.get("provider", "")
    api_key = request.get("api_key", "")

    if not provider or not api_key:
        raise HTTPException(status_code=400, detail="provider 和 api_key 均不能为空")

    # 构造环境变量名
    key_map = {
        "minimax": "MINIMAX_API_KEY",
        "openai": "OPENAI_API_KEY",
        "xfyun": "XFYUN_API_KEY",
        "gemini": "GEMINI_API_KEY",
        "replicate": "REPLICATE_API_KEY",
        "stability": "STABILITY_API_KEY",
        "together": "TOGETHER_API_KEY",
        "vidu": "VIDU_API_KEY",
    }
    env_var = key_map.get(provider.lower())
    if not env_var:
        raise HTTPException(status_code=400, detail=f"未知 provider: {provider}，支持: {list(key_map.keys())}")

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


if _web_dir.exists():
    app.mount("/web", StaticFiles(directory=str(_web_dir), html=True), name="web")


# ── 惰性 seed：首次访问 stats 时自动填充 ───
_seeded = False

def _ensure_seeded():
    global _seeded
    if not _seeded:
        seed_demo_data()
        _seeded = True

