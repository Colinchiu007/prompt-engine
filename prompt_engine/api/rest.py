"""FastAPI REST 服务层"""
from functools import lru_cache
from fastapi import FastAPI, HTTPException
from prompt_engine.optimizer import Optimizer
from prompt_engine.models import OptimizeRequest, BatchOptimizeRequest, OptimizeResult, ReverseRequest, ReverseResult, RewriteRequest

app = FastAPI(
    title="Prompt Engine API",
    description="图片生成提示词优化引擎 - REST API",
    version="0.4.0",
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