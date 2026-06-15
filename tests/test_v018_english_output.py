"""v0.18.0 — 中文输入自动英文输出"""
import re


class TestEnglishOutputRule:
    """中文输入 → 英文输出 测试."""

    strategies_imports = [
        "midjourney.MidjourneyStrategy",
        "stable_diffusion.StableDiffusionStrategy",
        "dalle.DalleStrategy",
        "tongyi.TongyiStrategy",
        "yizhang.YizhangStrategy",
        "jimeng.JimengStrategy",
        "generic.GenericStrategy",
    ]

    def test_all_strategies_have_english_output_rule(self):
        """所有策略的 system prompt 都应有强制英文输出规则"""
        from prompt_engine.strategies import midjourney, stable_diffusion
        from prompt_engine.strategies import dalle, tongyi, yizhang, jimeng, generic

        strategies = [
            midjourney.MidjourneyStrategy,
            stable_diffusion.StableDiffusionStrategy,
            dalle.DalleStrategy,
            tongyi.TongyiStrategy,
            yizhang.YizhangStrategy,
            jimeng.JimengStrategy,
            generic.GenericStrategy,
        ]
        for s in strategies:
            prompt = s.build_system_prompt(creative_level=5, max_length=300)
            # Either English keyword or Chinese 英文 keyword means the rule exists
            has_english_rule = (
                "English" in prompt or
                "english" in prompt or
                "英文" in prompt
            )
            # Check that output language is enforced
            has_output_instruction = (
                re.search(r"output\s.*in\s*English", prompt, re.IGNORECASE) or
                "english only" in prompt.lower() or
                "必须用" in prompt  # Chinese: "必须用英文输出"
            )
            assert has_english_rule, f"{s.__name__} missing English keyword"
            assert has_output_instruction, f"{s.__name__} missing output language instruction"

    def test_chinese_input_produces_english_output(self):
        """中文输入应输出英文（端到端 + mock LLM）"""
        from prompt_engine.optimizer import Optimizer
        from prompt_engine.models import OptimizeRequest
        from unittest.mock import patch

        with patch.object(Optimizer, "_call_llm") as mock_llm:
            mock_llm.return_value = ("A majestic feline on a velvet throne", 100)
            optimizer = Optimizer()
            req = OptimizeRequest(prompt="一只威严的猫", platform="midjourney", max_length=300)
            result = optimizer.optimize(req)
            assert "majestic feline" in result.optimized_prompt

    def test_midjourney_system_prompt_contains_chinese_to_english(self):
        """MJ 应提及中文→英文转换"""
        from prompt_engine.strategies.midjourney import MidjourneyStrategy
        prompt = MidjourneyStrategy.build_system_prompt(creative_level=5, max_length=300)
        assert "Chinese" in prompt or "中文" in prompt or "chinese" in prompt.lower()
