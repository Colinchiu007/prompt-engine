"""反馈驱动权重系统测试"""
import json
import os
import tempfile
from prompt_engine.models import FeedbackEntry
from prompt_engine.feedback import FeedbackStore


class TestFeedbackWeightSystem:
    """测试权重加载、保存和应用。"""

    def test_load_weights_empty(self):
        from prompt_engine.classifier import _load_keyword_weights
        weights = _load_keyword_weights()
        assert isinstance(weights, dict)

    def test_save_and_load_weights(self):
        from prompt_engine.classifier import _load_keyword_weights, _save_keyword_weights
        test_weights = {"lighting": {"volumetric": 1.2}, "design_styles": {"cyberpunk": 0.8}}
        _save_keyword_weights(test_weights)
        loaded = _load_keyword_weights()
        assert loaded["lighting"]["volumetric"] == 1.2
        assert loaded["design_styles"]["cyberpunk"] == 0.8
        # 清理
        os.unlink("keyword_weights.json")

    def test_apply_feedback_creates_weights(self):
        from prompt_engine.classifier import _apply_feedback_to_weights
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            fb_path = f.name
        try:
            # 写入一条反馈
            store = FeedbackStore(fb_path)
            store.submit(FeedbackEntry(
                prompt="golden retriever",
                detected_categories=["nature_and_animals"],
                corrected_categories=["nature_and_animals"],
                rating=5, method="keyword_match", confidence=0.8,
            ))
            count = _apply_feedback_to_weights(fb_path)
            assert count == 1
            from prompt_engine.classifier import _load_keyword_weights
            weights = _load_keyword_weights()
            assert "nature_and_animals" in weights
        finally:
            os.unlink(fb_path)
            if os.path.exists("keyword_weights.json"):
                os.unlink("keyword_weights.json")

    def test_weights_affect_classification(self):
        """验证权重影响分类结果。"""
        from prompt_engine.classifier import StyleCategoryClassifier, _get_weights, _save_keyword_weights
        # 给 nature_and_animals 一个强权重 boost
        _save_keyword_weights({"nature_and_animals": {"nature_and_animals": 2.0}})
        # 重置缓存
        import prompt_engine.classifier as c
        c._KEYWORD_WEIGHTS = None

        classifier = StyleCategoryClassifier()
        result = classifier.classify("nature scene with animals")
        assert any(c.value == "nature_and_animals" for c in result.categories)

        # 清理
        if os.path.exists("keyword_weights.json"):
            os.unlink("keyword_weights.json")
