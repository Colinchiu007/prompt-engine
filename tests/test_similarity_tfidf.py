"""v0.19.0 F3 — TF-IDF 缓存相似匹配测试"""
import pytest


class TestSimilarityTFIDF:
    """TF-IDF 余弦相似度匹配"""

    def _similarity(self, a: str, b: str) -> float:
        """调用 optimizer 中的 _similarity 函数"""
        from prompt_engine.optimizer import _similarity
        return _similarity(a, b)

    def test_exact_match_is_1(self):
        """精确匹配返回 1.0"""
        assert self._similarity("a cat", "a cat") == 1.0
        assert self._similarity("sunset over mountain", "sunset over mountain") == 1.0

    def test_case_insensitive(self):
        """大小写不影响"""
        s = self._similarity("A Cat", "a cat")
        assert s > 0.99  # 应接近 1.0

    def test_similar_prompts_high_score(self):
        """语义相似的 prompt 得分高"""
        s = self._similarity("a majestic cat sitting", "a cat sitting")
        assert s > 0.5, f"Similar prompts scored too low: {s}"

    def test_dissimilar_prompts_low_score(self):
        """不相关的 prompt 得分低"""
        s = self._similarity("a cat", "cyberpunk city neon lights")
        assert s < 0.6, f"Dissimilar prompts scored too high: {s}"

    def test_very_short_prompts(self):
        """极短 prompt 也能计算"""
        s = self._similarity("cat", "dog")
        # cat vs dog 应该有一定相似度（都是动物，字符 ngram 有重叠）
        assert s >= 0.0
        assert s <= 1.0

    def test_identical_meaning_different_words(self):
        """同义词应有一定相似度"""
        s = self._similarity("a quick brown fox", "a fast brown fox")
        assert s > 0.3, f"Synonyms scored too low: {s}"

    def test_fallback_on_error(self):
        """异常时降级到旧算法（不抛异常）"""
        from prompt_engine.optimizer import _similarity
        # 任何输入都不应抛异常
        try:
            s = _similarity("", "test")
            assert isinstance(s, float)
        except Exception as e:
            pytest.fail(f"_similarity raised exception: {e}")


class TestFuzzyMatchPrompt:
    """fuzzy_match_prompt 集成测试"""

    def test_fuzzy_match_returns_best(self):
        """fuzzy_match_prompt 找到最佳匹配"""
        from prompt_engine.optimizer import fuzzy_match_prompt
        from prompt_engine.models import OptimizeResult, PlatformType, StyleType

        # 先塞一个结果进缓存
        result = OptimizeResult(
            optimized_prompt="a majestic cat --ar 16:9",
            platform=PlatformType.MIDJOURNEY,
            style=StyleType.REALISTIC,
            model_used="test",
            tokens_used=100,
            duration_ms=500,
        )
        import prompt_engine.optimizer as opt_mod
        opt_mod._PromptCache[("a majestic cat", "midjourney", 7, 500, "", 1)] = result

        # 类似 prompt 应命中
        matched = fuzzy_match_prompt("a majestic cat", "midjourney", 7, 500, "", 1)
        assert matched is not None
        assert matched.optimized_prompt == "a majestic cat --ar 16:9"

        # 完全不同的应不命中
        not_matched = fuzzy_match_prompt("cyberpunk city", "midjourney", 7, 500, "", 1)
        assert not_matched is None

    def test_fuzzy_match_different_platform_doesnt_cross(self):
        """不同 platform 不交叉命中"""
        from prompt_engine.optimizer import fuzzy_match_prompt
        from prompt_engine.models import OptimizeResult, PlatformType, StyleType
        import prompt_engine.optimizer as opt_mod

        opt_mod._PromptCache[("a cat", "midjourney", 7, 500, "", 1)] = OptimizeResult(
            optimized_prompt="mj cat", platform=PlatformType.MIDJOURNEY,
            style=StyleType.REALISTIC, model_used="test", tokens_used=100, duration_ms=500,
        )

        matched = fuzzy_match_prompt("a cat", "stable_diffusion", 7, 500, "", 1)
        assert matched is None, "Different platform should not match"
