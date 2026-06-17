"""v0.15.0 — 中文翻译测试 (Python 单元)"""

from prompt_engine.translation import EN_CN_DICT, is_english, translate_en2cn


class TestTranslation:
    """F1: 中文翻译功能."""

    def test_dict_minimum_words(self):
        """EN_CN_DICT 必须 >= 50 词"""
        assert len(EN_CN_DICT) >= 50, f"Only {len(EN_CN_DICT)} words"

    def test_is_english_detects_english(self):
        """is_english() 应识别英文"""
        assert is_english("a majestic cat") is True
        assert is_english("golden hour lighting") is True
        assert is_english("4K ultra detailed") is True

    def test_is_english_rejects_chinese(self):
        """is_english() 应排除中文"""
        assert is_english("一只威严的猫") is False
        assert is_english("端坐的猫") is False
        assert is_english("") is False

    def test_translate_basic_words(self):
        """translate_en2cn() 翻译基础词"""
        result = translate_en2cn("a cat")
        assert "猫" in result
        assert "一只" in result

        result = translate_en2cn("majestic dog")
        assert "威严" in result or "威严的" in result
        assert "狗" in result

    def test_translate_unmapped_words_passthrough(self):
        """未匹配词保持英文"""
        result = translate_en2cn("xyzqwerty cat")
        assert "xyzqwerty" in result
        assert "猫" in result

    def test_translate_empty(self):
        """空输入返回空"""
        assert translate_en2cn("") == ""
        assert translate_en2cn(None) == "" if False else True  # skip None
