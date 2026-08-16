"""独立视频提示词优化引擎 REST API（端口 8020）。

端点：
- GET  /health                           健康检查
- POST /v1/video/optimize                单条优化（支持 output_language / num_candidates / context）
- POST /v1/video/optimize/batch          批量（≤20，有界并发 8，顺序一致）
- GET  /v1/video/platforms               已注册平台策略枚举
- GET  /v1/video/keywords                视频关键词词典（按维度）
- POST /v1/video/classify                输入题材/镜头意图检测
- POST /v1/video/feedback                好/坏反馈 → 种子库沉淀
- POST /v1/video/evaluate              确定性评分评测（1-20 条，可选双路对比）
- GET  /v1/video/cache/stats             双级缓存统计
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException

from video_prompt_engine.models import (
    VideoOptimizeRequest, VideoBatchOptimizeRequest,
    VideoFeedbackRequest, VideoClassifyRequest, VideoEvaluateRequest,
)
from video_prompt_engine.optimizer import VideoOptimizer
from video_prompt_engine.strategies import list_strategies
from video_prompt_engine.classifier import classify
from video_prompt_engine.evaluator import (
    evaluate as evaluate_prompt, _EVALUATOR_VERSION, detect_lang,
)

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
        return store.submit(
            request.prompt_text, request.result_prompt, request.good, request.source,
            failure_patterns=request.failure_patterns,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"feedback failed: {e}")


@app.get("/v1/video/cache/stats", response_model=dict)
def cache_stats():
    return get_optimizer().cache_stats()


def _compare_criteria(before: dict, after: dict) -> dict:
    """双路对比按判据的 delta：六要素/镜头维度/保真/违规扣分（仅输出有变化的判据）。"""
    b, a = before["checks"], after["checks"]
    delta: dict = {}
    for key, label in (
        ("length_points", "length"), ("elements_score", "elements"), ("has_shot", "shot"),
        ("has_camera", "camera"), ("has_motion", "motion"), ("fidelity", "fidelity"),
    ):
        bv, av = b.get(key), a.get(key)
        if isinstance(bv, bool):
            diff = (1 if av else 0) - (1 if bv else 0)
        elif isinstance(bv, (int, float)) and isinstance(av, (int, float)):
            diff = round(av - bv, 3)
        else:
            continue
        if diff:
            delta[label] = f"{diff:+}"
    b_penalty = sum((before.get("violations") or {}).values())
    a_penalty = sum((after.get("violations") or {}).values())
    if a_penalty != b_penalty:
        # 扣分总额差：正值=修复后少扣（正收益），与其余判据"正值=变好"同号（violations_penalty）
        delta["violations_penalty"] = f"{a_penalty - b_penalty:+}"
    return delta


@app.post("/v1/video/evaluate", response_model=dict)
def video_evaluate(request: VideoEvaluateRequest):
    """确定性评分评测（无 LLM）：逐条 evaluate() + 可选 compare 双路对比。

    评测口径默认 length_strict=False（长度不判失败，仅梯度提示）；detail=False 时 advice 关闭。
    """
    prompts = [p.strip() for p in request.prompts]
    if any(not p for p in prompts):
        raise HTTPException(status_code=422, detail="prompts 每条不允许为空")
    compares: list[str] | None = None
    if request.compare is not None:
        if len(request.compare) != len(prompts):
            raise HTTPException(
                status_code=422,
                detail=f"compare 长度 {len(request.compare)} 与 prompts 长度 {len(prompts)} 不一致",
            )
        compares = [c.strip() for c in request.compare]

    results = []
    for i, prompt in enumerate(prompts):
        # 评审 W4：language 缺省逐条自动判定（与哨兵脚本同一 detect_lang 口径），中文不再走 en 词数刻度
        lang = request.language or detect_lang(prompt)
        info = evaluate_prompt(
            prompt, {}, source_prompt="", language=lang,
            tier=request.tier, max_length=request.max_length,
            length_strict=request.length_strict, enable_advice=request.detail,
        )
        item: dict = {
            "index": i,
            "score": info["score"],
            "tier": info["tier"],
            "form": info["checks"].get("form"),
            "checks": info["checks"],
            "violations": info["violations"],
        }
        if request.detail:
            item["advice"] = info["advice"]
        if compares is not None:
            before = evaluate_prompt(
                compares[i], {}, source_prompt="", language=request.language or detect_lang(compares[i]),
                tier=request.tier, max_length=request.max_length,
                length_strict=request.length_strict, enable_advice=False,
            )
            item["compare"] = {
                # score_delta 是归一后总分差（含 /1.2），与 by_criterion 的原始判据差不对账（口径说明）
                "score_before": before["score"],
                "score_delta": round(info["score"] - before["score"], 1),
                "by_criterion": _compare_criteria(before, info),
            }
        results.append(item)
    # evaluator 版本标识：确定性规则评分器（v0.11 起），与 app version 无对应关系
    return {"results": results, "meta": {"count": len(results), "evaluator": _EVALUATOR_VERSION}}
