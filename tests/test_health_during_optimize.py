"""回归：长耗时 optimize 期间事件循环不得被阻塞

背景：/v1/optimize 此前在 async 端点内同步调用 optimizer.optimize（含 LLM 网络等待），
阻塞事件循环使 /health 在优化期间超时，Bridge watchdog 误判 unhealthy 并重启服务，
打断在途优化请求导致图片轮播流水线报错。修复后优化在线程池执行。
"""
import asyncio
import time

import httpx
import pytest

from prompt_engine.api import rest


class SlowOptimizer:
    """模拟 2s 的 LLM 优化耗时"""

    def __init__(self):
        self._provider = type("P", (), {"model_name": "slow"})()
        self._provider._key_source = "test"

    def optimize(self, request):
        time.sleep(2)
        from prompt_engine.models import OptimizeResult
        return OptimizeResult(
            optimized_prompt="ok prompt",
            platform=request.platform,
            style=request.style,
            model_used="slow",
        )

    def optimize_with_key_router(self, request, provider):
        return self.optimize(request)


@pytest.mark.asyncio
async def test_health_responsive_while_optimize_in_flight(monkeypatch):
    monkeypatch.setattr(rest, "get_optimizer", lambda: SlowOptimizer())
    transport = httpx.ASGITransport(app=rest.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        t0 = time.time()
        health_task = asyncio.create_task(client.get("/health"))
        await asyncio.sleep(0.2)  # 让 optimize 先开始阻塞旧实现
        opt_task = asyncio.create_task(
            client.post("/v1/optimize", json={"prompt": "a cat", "platform": "generic", "style": "realistic"})
        )
        health = await health_task
        health_latency = time.time() - t0
        # 修复前：health 会被 optimize 的同步调用阻塞 ~2s；修复后应立即返回
        assert health.status_code == 200
        assert health_latency < 1.5, f"health 被 optimize 阻塞: {health_latency:.2f}s"
        opt = await opt_task
        assert opt.status_code == 200
        assert opt.json()["optimized_prompt"] == "ok prompt"


@pytest.mark.asyncio
async def test_concurrent_optimizes_run_in_parallel(monkeypatch):
    monkeypatch.setattr(rest, "get_optimizer", lambda: SlowOptimizer())
    transport = httpx.ASGITransport(app=rest.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        t0 = time.time()
        results = await asyncio.gather(
            client.post("/v1/optimize", json={"prompt": "a cat", "platform": "generic", "style": "realistic"}),
            client.post("/v1/optimize", json={"prompt": "a dog", "platform": "generic", "style": "realistic"}),
        )
        elapsed = time.time() - t0
        assert all(r.status_code == 200 for r in results)
        # 修复前两个 2s 请求串行 ~4s；修复后并行 ~2s
        assert elapsed < 3.5, f"两个 optimize 未并行执行: {elapsed:.2f}s"
