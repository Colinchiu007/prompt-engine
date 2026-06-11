"""FastAPI REST 服务层"""
from functools import lru_cache
from fastapi import FastAPI, HTTPException
from prompt_engine.optimizer import Optimizer
from prompt_engine.models import OptimizeRequest, BatchOptimizeRequest, OptimizeResult

app = FastAPI(
    title="Prompt Engine API",
    description="图片生成提示词优化引擎 - REST API",
    version="0.1.0",
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


@app.get("/v1/platforms")
async def list_platforms():
    """列出支持的所有平台"""
    from prompt_engine.strategies import list_strategies
    strategies = list_strategies()
    return {"platforms": strategies, "count": len(strategies)}


@app.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "ok", "version": "0.1.0"}