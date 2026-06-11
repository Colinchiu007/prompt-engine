"""Optimizer — 核心编排器"""
import time
from typing import Optional
from prompt_engine.models import OptimizeRequest, OptimizeResult
from prompt_engine.config import load_config
from prompt_engine.strategies import get_strategy
from prompt_engine.llm.base import BaseLLMProvider


class Optimizer:
    """提示词优化引擎核心类"""

    def __init__(self, config: Optional[dict] = None):
        self.config = config or load_config()
        self._provider = BaseLLMProvider.from_config(self.config)

    def optimize(self, request: OptimizeRequest) -> OptimizeResult:
        """单条提示词优化主流程"""
        start_time = time.time()
        try:
            # 1. 加载平台策略
            strategy_cls = get_strategy(request.platform.value)
            if not strategy_cls:
                strategy_cls = get_strategy("generic")

            # 2. 构建系统提示词（含负面提示词）
            system_prompt = strategy_cls.build_system_prompt(
                style=request.style,
                creative_level=request.creative_level,
                max_length=request.max_length,
                negative_prompt=request.negative_prompt,
            )

            # 3. 调用 LLM
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": request.prompt},
            ]
            raw_output, tokens_used = self._provider.chat(messages)

            # 4. 后处理 + 长度截断
            optimized = strategy_cls.post_process(raw_output)
            if len(optimized) > request.max_length:
                optimized = optimized[:request.max_length]

            elapsed = (time.time() - start_time) * 1000

            return OptimizeResult(
                optimized_prompt=optimized,
                platform=request.platform,
                style=request.style,
                model_used=self._provider.model_name,
                tokens_used=tokens_used,
                duration_ms=round(elapsed, 1),
            )
        except Exception as e:
            elapsed = (time.time() - start_time) * 1000
            return OptimizeResult(
                optimized_prompt=request.prompt,
                platform=request.platform,
                style=request.style,
                model_used=self._provider.model_name,
                tokens_used=0,
                duration_ms=round(elapsed, 1),
                error=str(e),
            )