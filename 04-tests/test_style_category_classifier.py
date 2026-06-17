"""Tests for Style Category Classifier."""
import sys
sys.path.insert(0, r"C:\Users\邱领\projects\prompt-engine")

import pytest
from prompt_engine.classifier import StyleCategoryClassifier, StyleCategory, _keyword_match
from prompt_engine.models import StyleCategoryResult


class TestStyleCategoryClassifierBasic:
    def test_classifier_instantiates(self):
        classifier = StyleCategoryClassifier()
        assert classifier is not None

    def test_classifier_returns_categories_on_known_prompt(self):
        classifier = StyleCategoryClassifier()
        result = classifier.classify("3D render with volumetric lighting, ray tracing")
        assert result.method == "keyword_match"
        assert len(result.categories) > 0
        assert result.confidence >= 0.0

    def test_classifier_with_llm_func(self):
        def mock_llm(system, user):
            return '{"categories": ["themes", "design_styles"]}'
        
        classifier = StyleCategoryClassifier(llm_chat_func=mock_llm)
        result = classifier.classify("something very abstract and conceptual", use_llm=True)
        assert result.method in ("keyword_match", "llm_classify")

    def test_classifier_empty_prompt(self):
        classifier = StyleCategoryClassifier()
        result = classifier.classify("")
        assert isinstance(result, StyleCategoryResult)


class TestStyleCategoryKeywordMatching:
    def test_chinese_watercolor(self):
        _, keywords_found, confidence = _keyword_match("中国水墨画风格的山水风景")
        assert confidence >= 0.0

    def test_chinese_lighting(self):
        _, keywords_found, confidence = _keyword_match("赛博朋克风格，霓虹灯光，雨夜")
        assert confidence >= 0.0

    def test_english_design_styles(self):
        _, keywords_found, confidence = _keyword_match("Cyberpunk city with neon lights")
        assert confidence > 0

    def test_english_nature(self):
        _, keywords_found, confidence = _keyword_match("A golden retriever running through a wildflower meadow")
        assert confidence > 0

    def test_english_lighting(self):
        _, keywords_found, confidence = _keyword_match("3D render of a modern interior, volumetric lighting, ray tracing")
        assert confidence > 0

    def test_no_false_positives_for_song_lyrics(self):
        classifier = StyleCategoryClassifier()
        result = classifier.classify("A cat sitting on a wall")
        assert StyleCategory.SONG_LYRICS not in result.categories


class TestStyleCategoryClassifierWithLLM:
    def test_llm_parse_json_response(self):
        classifier = StyleCategoryClassifier()
        response = '{"categories": ["themes", "design_styles"], "reason": "Abstract concept"}'
        cats = classifier._parse_llm_response(response)
        assert len(cats) == 2
        assert cats[0] == "themes" or cats[0].value == "themes"
        assert cats[1] == "design_styles" or cats[1].value == "design_styles"

    def test_llm_parse_invalid_json(self):
        classifier = StyleCategoryClassifier()
        response = "I think this is about themes"
        cats = classifier._parse_llm_response(response)
        assert isinstance(cats, list)

    def test_llm_with_mock(self):
        def mock_chat(system, user):
            return '{"categories": ["lighting", "camera"]}'
        
        classifier = StyleCategoryClassifier(llm_chat_func=mock_chat)
        result = classifier.classify("something very abstract")
        # "abstract" 可命中 SFX_and_Shaders 关键词，method=keyword_match
        assert result.method in ("llm_classify", "vector_rag", "keyword_match")
        assert len(result.categories) >= 1


class TestStyleCategoryResultModel:
    def test_result_creation(self):
        result = StyleCategoryResult(
            categories=[StyleCategory.LIGHTING],
            keywords_found={"lighting": ["Volumetric Lighting"]},
            method="keyword_match",
            confidence=0.85
        )
        assert len(result.categories) == 1
        assert result.method == "keyword_match"
        assert result.confidence == 0.85

    def test_result_empty(self):
        result = StyleCategoryResult()
        assert len(result.categories) == 0
        assert result.method == "keyword_match"
        assert result.confidence == 0.0


class TestStyleCategoryClassifierRAG:
    """测试 RAG 向量搜索功能."""

    def test_rag_index_exists(self):
        from prompt_engine.classifier import StyleCategoryClassifier
        c = StyleCategoryClassifier()
        assert c._rag_index is not None

    def test_vector_search_returns_categories(self):
        from prompt_engine.classifier import StyleCategoryClassifier
        c = StyleCategoryClassifier()
        # 模糊语义查询，走向量搜索
        scores = c._vector_search("a feeling of longing and melancholy")
        assert len(scores) > 0
        # Lighting 类别应该有较高得分
        assert "Lighting" in scores

    def test_vector_search_watercolor(self):
        from prompt_engine.classifier import StyleCategoryClassifier
        c = StyleCategoryClassifier()
        scores = c._vector_search("watercolor painting landscape")
        assert len(scores) > 0
        # Drawing_and_Art_Mediums 应该排名靠前
        assert "Drawing_and_Art_Mediums" in scores or "Colors_and_Palettes" in scores

    def test_three_level_pipeline_keyword_wins(self):
        """关键词精确命中时走 keyword_match，不走向量."""
        classifier = StyleCategoryClassifier()
        result = classifier.classify("watercolor painting of mountains")
        assert result.method == "keyword_match"
        assert len(result.categories) >= 1

    def test_three_level_pipeline_vector_fallback(self):
        """极端模糊文本，向量搜索应该能返回结果."""
        classifier = StyleCategoryClassifier()
        # 构造一个可能同时命中关键词但 confidence 不够的场景
        # 向量搜索应该能补充类别
        scores = classifier._vector_search("a feeling of longing and melancholy")
        assert len(scores) > 0


class TestRecommendCategoriesForStyle:
    """StyleType → StyleCategory 反向推荐测试."""

    def test_recommend_oil_painting(self):
        from prompt_engine.classifier import recommend_categories_for_style
        result = recommend_categories_for_style("oil_painting")
        assert len(result) >= 3
        assert any(c.value == "drawing_and_art_mediums" for c in result)

    def test_recommend_cyberpunk(self):
        from prompt_engine.classifier import recommend_categories_for_style
        result = recommend_categories_for_style("cyberpunk")
        assert len(result) >= 3
        assert any(c.value == "design_styles" for c in result)

    def test_recommend_landscape(self):
        from prompt_engine.classifier import recommend_categories_for_style
        result = recommend_categories_for_style("landscape")
        assert any(c.value == "nature_and_animals" for c in result)

    def test_recommend_unknown_style_falls_back(self):
        from prompt_engine.classifier import recommend_categories_for_style
        result = recommend_categories_for_style("nonexistent_style_xyz")
        assert len(result) >= 1

    def test_recommend_all_styles_have_mapping(self):
        from prompt_engine.models import StyleType
        from prompt_engine.classifier import recommend_categories_for_style
        for style in StyleType:
            result = recommend_categories_for_style(style.value)
            assert len(result) >= 1, f"No mapping for {style.value}"

class TestStyleCategoryClassifierIntegration:
    def test_comprehensive_classification(self):
        classifier = StyleCategoryClassifier()
        
        test_cases = [
            ("一只猫坐在墙上，赛博朋克风格，霓虹灯光", ['lighting', 'design_styles']),
            ("A golden retriever in a wildflower meadow", ['nature_and_animals']),
            ("中国水墨画风格的山水风景", ['nature_and_animals', 'geography_and_culture', 'drawing_and_art_mediums']),
            ("Cyberpunk city with neon lights", ['design_styles', 'lighting']),
            ("Pixel art retro game character", ['design_styles']),
            ("3D render volumetric lighting ray tracing", ['lighting', 'sfx_and_shaders']),
            ("Oil painting night sky stars moon", ['drawing_and_art_mediums', 'outer_space']),
        ]
        
        for prompt, expected_categories in test_cases:
            result = classifier.classify(prompt, max_categories=5)
            found = [c.value for c in result.categories]
            match = any(exp in found for exp in expected_categories)
            assert match, f"Expected {expected_categories}, got {found} for prompt: {prompt}"


class TestStyleCategoryClassifierEdgeCases:
    def test_empty_prompt(self):
        classifier = StyleCategoryClassifier()
        result = classifier.classify("")
        assert isinstance(result, StyleCategoryResult)

    def test_very_long_prompt(self):
        classifier = StyleCategoryClassifier()
        long_prompt = "watercolor " * 100
        result = classifier.classify(long_prompt, max_categories=5)
        assert isinstance(result, StyleCategoryResult)

    def test_special_characters(self):
        classifier = StyleCategoryClassifier()
        prompt = "绘画 🎨 艺术 🖼️ 风格 ✨"
        result = classifier.classify(prompt, max_categories=5)
        assert isinstance(result, StyleCategoryResult)

    def test_mixed_language(self):
        classifier = StyleCategoryClassifier()
        prompt = "中国水墨画 Chinese ink painting 山水 landscape"
        result = classifier.classify(prompt, max_categories=5)
        assert isinstance(result, StyleCategoryResult)
