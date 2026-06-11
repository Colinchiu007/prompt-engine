"""FastAPI REST 服务层"""
from fastapi import FastAPI, HTTPException
from prompt_engine.optimizer import Optimizer
from prompt_engine.models import OptimizeRequest, OptimizeResult

app = FastAPI(
    title="Prompt Engine API",
    description="图片生成提示词优化引擎 - REST API",
    version="0.1.0",
)

_optimizer: Optimizer | None = None


def get_optimizer() -> Optimizer:
    global _optimizer
    if _optimizer is None:
        _optimizer = Optimizer()
    return _optimizer


@app.post("/v1/optimize", response_model=OptimizeResult)
async def optimize(request: OptimizeRequest):
    """优化单条提示词

    - **prompt**: 原始提示词（必填，1-2000 字符）
    - **platform**: 目标平台（默认 generic）
    - **style**: 艺术风格（可选）
    - **creative_level**: 创意程度 1-10（默认 5）
    - **max_length**: 最大字符数（默认 500）
    """
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