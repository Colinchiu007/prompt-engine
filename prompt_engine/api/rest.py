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
