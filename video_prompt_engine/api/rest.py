"""独立视频提示词优化引擎 REST API（端口 8020）。

端点：
- GET  /health
- POST /v1/video/optimize          单条优化
- POST /v1/video/optimize/batch    批量（≤20，有界并发 8，顺序一致）
- GET  /v1/video/platforms         平台枚举
- GET  /v1/video/keywords          视频关键词词典（按维度）
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException

from video_prompt_engine.models import (
    VideoOptimizeRequest, VideoBatchOptimizeRequest, VideoPlatformType,
    normalize_video_platform,
)
from video_prompt_engine.optimizer import VideoOptimizer

app = FastAPI(title="Video Prompt Engine", version="0.1.0")
_optimizer: VideoOptimizer | None = None


def get_optimizer() -> VideoOptimizer:
    global _optimizer
    if _optimizer is None:
        _optimizer = VideoOptimizer()
    return _optimizer


@app.get("/health")
def health():
    return {"status": "ok", "engine": "video", "version": "0.1.0"}


@app.get("/v1/video/platforms")
def platforms():
    return {"platforms": [p.value for p in VideoPlatformType]}


@app.get("/v1/video/keywords")
def keywords():
    optimizer = get_optimizer()
    return {"dimensions": {dim: entries[:50] for dim, entries in optimizer._keywords.items()}}


@app.post("/v1/video/optimize", response_model=dict)
def optimize(request: VideoOptimizeRequest):
    result = get_optimizer().optimize(request)
    if result.error:
        raise HTTPException(status_code=502, detail=result.error)
    return result.model_dump(exclude_none=True)


@app.post("/v1/video/optimize/batch", response_model=list[dict])
def optimize_batch(request: VideoBatchOptimizeRequest):
    # 有界并发 8（ThreadPoolExecutor），结果顺序与请求一致
    optimizer = get_optimizer()
    results = optimizer.optimize_batch(request.requests)
    return [r.model_dump(exclude_none=True) for r in results]
