"""独立视频提示词优化引擎 REST API（端口 8020）。

端点：
- GET  /health                           健康检查
- POST /v1/video/optimize                单条优化（支持 output_language / num_candidates / context）
- POST /v1/video/optimize/batch          批量（≤20，有界并发 8，顺序一致）
- GET  /v1/video/platforms               已注册平台策略枚举
- GET  /v1/video/keywords                视频关键词词典（按维度）
- POST /v1/video/classify                输入题材/镜头意图检测
- POST /v1/video/feedback                好/坏反馈 → 种子库沉淀
- GET  /v1/video/cache/stats             双级缓存统计
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException

from video_prompt_engine.models import (
    VideoOptimizeRequest, VideoBatchOptimizeRequest,
    VideoFeedbackRequest, VideoClassifyRequest,
)
from video_prompt_engine.optimizer import VideoOptimizer
from video_prompt_engine.strategies import list_strategies
from video_prompt_engine.classifier import classify

app = FastAPI(title="Video Prompt Engine", version="0.2.0")
_optimizer: VideoOptimizer | None = None


def get_optimizer() -> VideoOptimizer:
    global _optimizer
    if _optimizer is None:
        _optimizer = VideoOptimizer()
    return _optimizer


@app.get("/health")
def health():
    return {"status": "ok", "engine": "video", "version": "0.2.0"}


@app.get("/v1/video/platforms")
def platforms():
    """返回实际已注册的平台策略（未知平台由 optimizer 回退 generic_video）。"""
    return {"platforms": list_strategies()}


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


@app.post("/v1/video/classify", response_model=dict)
def video_classify(request: VideoClassifyRequest):
    """输入题材/镜头意图检测（自动选策略与关键词维度的依据）。"""
    return classify(request.prompt)


@app.post("/v1/video/feedback", response_model=dict)
def video_feedback(request: VideoFeedbackRequest):
    """好/坏反馈闭环：好评结果沉淀入种子库；坏评源提示词质量分降级。"""
    try:
        # 反馈沉淀到可写数据目录（默认缓存目录，env VIDEO_FEEDBACK_PATH 覆盖），
        # 避免写入 wheel 包内只读的 knowledge/seed_video_prompts.json。
        import os
        from pathlib import Path
        from video_prompt_engine.feedback import VideoFeedbackStore
        default_dir = get_optimizer().config.get("cache", {}).get("dir", "video_prompt_cache")
        p = Path(default_dir)
        if not p.is_absolute():
            p = Path(__file__).parent.parent.parent / p
        seed_path = Path(os.environ.get("VIDEO_FEEDBACK_PATH", str(p / "feedback_seed.json")))
        store = VideoFeedbackStore(seed_path)
        return store.submit(request.prompt_text, request.result_prompt, request.good, request.source)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"feedback failed: {e}")


@app.get("/v1/video/cache/stats", response_model=dict)
def cache_stats():
    return get_optimizer().cache_stats()
