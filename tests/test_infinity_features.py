"""测试 Prompt Rewriter、BitwiseClassifier、Prompt Disturber"""
import pytest
import torch
from unittest.mock import patch, MagicMock
from prompt_engine.models import OptimizeRequest, PlatformType
from prompt_engine.optimizer import Optimizer
from prompt_engine.rewriter import PromptRewriter
from prompt_engine.disturb import disturb_prompt, PromptDisturber
from prompt_engine.classifier import BitwiseClassifier


class TestPromptRewriter:
    """测试 Infinity 灵感的 prompt 扩写"""

    def test_rewrite_short_prompt(self):
        from prompt_engine.llm.base import BaseLLMProvider
        mock_provider = MagicMock(spec=BaseLLMProvider)
        mock_provider.chat.return_value = (
            '<prompt:A stunning morning scene in a peaceful meadow with golden sunlight filtering through tall grass><cfg:3>',
            100,
        )
        rewriter = PromptRewriter(mock_provider)
        result = rewriter.rewrite("morning meadow")
        assert "meadow" in result.lower() or "stunning" in result.lower()
        assert len(result) > len("morning meadow")

    def test_rewrite_short_to_long(self):
        from prompt_engine.llm.base import BaseLLMProvider
        mock_provider = MagicMock(spec=BaseLLMProvider)
        mock_provider.chat.return_value = (
            '<prompt:A beautiful sunset over the ocean with waves crashing against rocks and seagulls flying overhead><cfg:3>',
            100,
        )
        rewriter = PromptRewriter(mock_provider)
        result = rewriter.rewrite_raw("sunset")
        assert len(result) > 30

    def test_rewrite_fallback_on_error(self):
        from prompt_engine.llm.base import BaseLLMProvider
        mock_provider = MagicMock(spec=BaseLLMProvider)
        mock_provider.chat.side_effect = RuntimeError("API error")
        rewriter = PromptRewriter(mock_provider)
        result = rewriter.rewrite_raw("test")
        assert result == "test"


class TestPromptDisturber:
    """测试 prompt 扰动增强"""

    def test_disturb_synonym_replacement(self):
        result = disturb_prompt("a beautiful tree", strength=0.5)
        assert result != "a beautiful tree"
        # 词数应该相近
        orig_words = len("a beautiful tree".split())
        result_words = len(result.split())
        assert abs(orig_words - result_words) <= 2

    def test_disturb_preserves_meaning(self):
        result = disturb_prompt("a cute cat", strength=0.3)
        assert len(result) > 0
        assert len(result.split()) >= 2

    def test_disturb_no_change_low_strength(self):
        result = disturb_prompt("short", strength=0.0)
        assert result == "short"

    def test_disturb_empty_prompt(self):
        result = disturb_prompt("", strength=0.5)
        assert result == ""

    def test_disturb_batch(self):
        disturb = PromptDisturber(strength=0.5)
        results = disturb.perturb_batch(["a beautiful tree in the forest", "a cat"], num_augmented=2)
        assert "a beautiful tree in the forest" in results
        assert "a cat" in results
        # 长 prompt 至少有 1 个增强（短的可能因去重为空）
        assert len(results["a beautiful tree in the forest"]) >= 1

    def test_disturb_different_from_original(self):
        disturb = PromptDisturber(strength=0.5)
        original = "a beautiful morning in the forest with sunlight"
        perturbed = disturb.perturb(original)
        assert perturbed != original


class TestBitwiseClassifier:
    """测试 Infinity IVC 灵感的比特级分类器"""

    def test_bits_count(self):
        clf = BitwiseClassifier(embed_dim=64, num_classes=8)
        assert clf.num_bits == 3  # log2(8) = 3

    def test_bits_count_for_non_power_of_two(self):
        clf = BitwiseClassifier(embed_dim=64, num_classes=5)
        assert clf.num_bits == 3  # ceil(log2(5)) = 3

    def test_forward_shape(self):
        clf = BitwiseClassifier(embed_dim=32, num_classes=16)
        x = torch.randn(4, 32)
        logits = clf(x)
        assert logits.shape == (4, 4, 2)  # (B, num_bits, 2)

    def test_decode(self):
        clf = BitwiseClassifier(embed_dim=32, num_classes=8)
        # 直接构造 logits: class 5 -> bits 101
        logits = torch.zeros(1, 3, 2)
        logits[0, 0, 0] = 1  # bit 0 = 0
        logits[0, 1, 1] = 1  # bit 1 = 1
        logits[0, 2, 0] = 1  # bit 2 = 0
        decoded = clf.decode(logits)
        assert decoded[0].item() == 2  # 010 = 2

    def test_loss_shape(self):
        clf = BitwiseClassifier(embed_dim=32, num_classes=4)
        x = torch.randn(8, 32)
        logits = clf(x)
        targets = torch.zeros(8, dtype=torch.long)
        loss = clf.loss(logits, targets)
        assert loss.dim() == 0
        assert loss.item() > 0  # random logits should have non-zero loss

    def test_param_savings(self):
        """验证参数量远小于传统分类器"""
        clf = BitwiseClassifier(embed_dim=1024, num_classes=1000)
        # 传统: 1000*1024 = 1M
        # 比特: 10*2*1024 = 20K
        traditional = 1000 * 1024
        bitwise = clf.num_bits * 2 * 1024
        assert bitwise < traditional / 20  # 至少省 20 倍

    def test_from_config(self):
        clf = BitwiseClassifier.from_config(embed_dim=64, num_classes=16)
        assert clf.num_classes == 16
