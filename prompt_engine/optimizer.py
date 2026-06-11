"""Optimizer — 核心编排器"""
from typing import Optional
from prompt_engine.models import (
    OptimizeRequest, OptimizeResult, PlatformType, StyleType,
)
from prompt_engine.config import load_config
from prompt_engine.strategies import get_strategy
from prompt_engine.llm import get_provider


class Optimizer:
    """提示词优化引擎核心类"""

    def __init__(self, config: Optional[dict] = None):
        self.config = config or load_config()
        self._provider = get_provider(self.config)

    def optimize(self, request: OptimizeRequest) -> OptimizeResult:
        """单条提示词优化主流程"""
        try:
            # 1. 加载平台策略
            strategy_cls = get_strategy(request.platform.value)
            if not strategy_cls:
                # 回退到通用策略
                strategy_cls = get_strategy("generic")

            # 2. 构建系统提示词
            system_prompt = strategy_cls.build_system_prompt(
                style=request.style,
                creative_level=request.creative_level,
                max_length=request.max_length,
            )

            # 3. 调用 LLM
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": request.prompt},
            ]
            raw_output = self._provider.chat(messages)

            # 4. 后处理
            optimized = strategy_cls.post_process(raw_output)

            return OptimizeResult(
                optimized_prompt=optimized,
                platform=request.platform,
                style=request.style,
                model_used=self._provider.model_name,
                tokens_used=0,  # TODO: 从响应中解析 token 数
            )
        except Exception as e:
            # 降级：返回原词 + 错误信息
            return OptimizeResult(
                optimized_prompt=request.prompt,
                platform=request.platform,
                style=request.style,
                model_used=self._provider.model_name,
                tokens_used=0,
                error=str(e),
            )
