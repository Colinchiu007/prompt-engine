"""推理块剥离回归测试 — <think> 内容不得进入 optimized_prompt

背景：MiniMax-M3 等推理模型会把 <think> 思考过程放进返回内容，甚至整段输出只有推理
（max_tokens 被推理耗尽、无 </think> 闭合）。此前 prompt-engine 原样返回，
下游 Story2Video 把剥离后的空提示词判为失败，图片轮播流水线一直报错。
"""
import uuid
from unittest.mock import patch, MagicMock

from prompt_engine.optimizer import Optimizer, strip_reasoning_blocks
from prompt_engine.models import OptimizeRequest, PlatformType


def _mock_provider(model_name="mock-model"):
    p = MagicMock()
    p.model_name = model_name
    return p


def _unique_prompt(base="test"):
    return f"{base} {uuid.uuid4().hex[:8]}"


class TestStripReasoningBlocks:
    def test_complete_think_block_keeps_after_content(self):
        raw = "<think>Let me analyze the scene.</think>A white egret standing in shallow water at dawn, soft light"
        assert strip_reasoning_blocks(raw) == "A white egret standing in shallow water at dawn, soft light"

    def test_think_only_output_returns_empty(self):
        raw = "<think>The user wants me to transform this into an English prompt. Let me analyze..."
        assert strip_reasoning_blocks(raw) == ""

    def test_no_think_block_unchanged(self):
        raw = "A white egret standing in shallow water at dawn, realistic"
        assert strip_reasoning_blocks(raw) == raw

    def test_multiple_think_blocks_removed(self):
        raw = "<think>first</think>content<think>second</think> tail"
        assert strip_reasoning_blocks(raw) == "content tail"

    def test_think_with_leading_text(self):
        raw = "prefix <think>hidden</think> real prompt"
        assert strip_reasoning_blocks(raw) == "prefix  real prompt"


class TestOptimizerReasoningFallback:
    @patch.object(Optimizer, "_call_llm")
    def test_think_block_stripped_before_result(self, mock_call):
        mock_call.return_value = (
            "<think>Let me analyze.</think>An orange cat chasing a butterfly in the meadow, warm sunlight",
            200,
        )
        optimizer = Optimizer()
        req = OptimizeRequest(prompt=_unique_prompt(), platform=PlatformType.GENERIC, creative_level=5)
        result = optimizer.optimize(req, provider=_mock_provider())
        assert "orange cat" in result.optimized_prompt
        assert "<think>" not in result.optimized_prompt

    @patch.object(Optimizer, "_call_llm")
    def test_think_only_output_falls_back_to_original(self, mock_call):
        mock_call.return_value = (
            "<think>The user wants me to transform this Chinese description into an English prompt. "
            "Let me carefully analyze the scene details and compose a rich image generation prompt "
            "with proper lighting, composition, camera and style descriptors...",
            500,
        )
        optimizer = Optimizer()
        prompt = _unique_prompt("清晨的湖边")
        req = OptimizeRequest(prompt=prompt, platform=PlatformType.GENERIC, creative_level=5)
        result = optimizer.optimize(req, provider=_mock_provider())
        assert result.optimized_prompt == prompt
        # BYOK: pure reasoning content no longer falls back silently, errors instead
        # assert result.error is None  # old behavior
