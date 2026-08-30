"""回归（2026-08-20）：LLM 只输出推理块时，optimizer 不再整线失败。

背景：推理模型（如 DeepSeek）可能把完整思考过程放进推理标签而不给最终提示词。
prompt-engine 剥离后内容为空时，旧逻辑立即抛 RuntimeError，导致被调用方
（如 Multi-Publish 视频流水线）整线失败。

修复语义（引擎层，独立调用方同样受益）：
- 剥离后为空先有界重试（最多 3 次）；
- 重试后仍为空则回退原文，不抛错。

说明：strip_reasoning_blocks 由 prompt_engine_core.text 提供（推理标签样式由
其维护）。本测试用 monkeypatch 将剥离函数收敛为确定性桩（含 "REASONING_ONLY"
标记即视为纯推理、剥离后为空），从而聚焦验证 optimizer 自身的重试 / 回退控制流。
"""
import prompt_engine.optimizer as optimizer_module
from prompt_engine.optimizer import Optimizer
from prompt_engine.models import OptimizeRequest, PlatformType
from prompt_engine.llm.base import BaseLLMProvider
from types import SimpleNamespace


class _StubProvider(BaseLLMProvider):
    """极简 provider：按队列顺序返回预设 (text, tokens)。"""

    def __init__(self, queue=None):
        self.config = {}
        self._queue = list(queue or [])

    @property
    def model_name(self):
        return "stub"

    def chat(self, messages):
        return self._queue.pop(0)


def _install_strip_stub(monkeypatch):
    original = optimizer_module.strip_reasoning_blocks

    def fake_strip(text):
        value = text or ""
        if "REASONING_ONLY" in value:
            return ""
        return original(value)

    monkeypatch.setattr(optimizer_module, "strip_reasoning_blocks", fake_strip)


def _run(queue, prompt, monkeypatch):
    _install_strip_stub(monkeypatch)
    optimizer = Optimizer()
    monkeypatch.setattr(
        optimizer, "_render_from_template",
        lambda _req: SimpleNamespace(optimized_prompt="template-optimized:" + prompt),
    )
    req = OptimizeRequest(
        prompt=prompt,
        platform=PlatformType.GENERIC,
        creative_level=5,
        bypass_cache=True,
    )
    return optimizer.optimize(req, provider=_StubProvider(queue), provider_id="stub")


def test_pure_reasoning_blocks_fall_back_to_template(monkeypatch):
    queue = [
        ("REASONING_ONLY first", 10),
        ("REASONING_ONLY second", 10),
        ("REASONING_ONLY third", 10),
    ]
    result = _run(queue, "原文A", monkeypatch)
    assert result.optimized_prompt.startswith("template-optimized:")
    assert result.optimized_prompt != "原文A"
    assert result.error is None


def test_first_reasoning_then_valid_retries(monkeypatch):
    queue = [
        ("REASONING_ONLY", 5),
        ("real optimized prompt", 20),
    ]
    result = _run(queue, "原文B", monkeypatch)
    assert "real optimized prompt" in result.optimized_prompt


def test_plain_valid_prompt_passes_through(monkeypatch):
    queue = [("plain valid prompt", 15)]
    result = _run(queue, "原文C", monkeypatch)
    assert "plain valid prompt" in result.optimized_prompt
