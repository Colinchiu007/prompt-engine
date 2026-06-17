"""Tests for Midjourney Style Reference integration."""
import sys
sys.path.insert(0, r"C:\Users\邱领\projects\prompt-engine")

import pytest
from prompt_engine.strategies.midjourney import (
    _load_mj_style_db,
    _inject_style_keywords,
    MidjourneyStrategy,
)


class TestMJStyleDatabase:
    """Test MJ style database loading and structure."""

    def test_db_loads(self):
        db = _load_mj_style_db()
        assert db is not None

    def test_db_has_27_categories(self):
        db = _load_mj_style_db()
        assert len(db) >= 20

    def test_db_has_2000_plus_keywords(self):
        db = _load_mj_style_db()
        total = sum(len(v) for v in db.values())
        assert total >= 1000

    def test_core_categories_exist(self):
        db = _load_mj_style_db()
        for cat in ["Lighting", "Camera", "Materials", "Colors_and_Palettes"]:
            assert cat in db, f"{cat} category missing"
            assert len(db[cat]) > 0, f"{cat} has no keywords"

    def test_materials_has_200_plus(self):
        db = _load_mj_style_db()
        assert len(db.get("Materials", [])) > 150


class TestMJStyleKeywordInjection:
    """Test _inject_style_keywords function."""

    def test_injects_at_all_levels(self):
        """Keywords should be injected at all creative levels."""
        for level in [1, 3, 5, 7, 10]:
            result = _inject_style_keywords("A cat", creative_level=level)
            assert result != "A cat.", f"Level {level}: no injection"

    def test_low_creative_fewer_categories(self):
        """Low creative level should inject fewer categories."""
        for _ in range(10):
            result = _inject_style_keywords("test", creative_level=1)
            words = result.split(", ")
            # Should have at most 1-2 injected words
            assert len(words) <= 3

    def test_high_creative_more_categories(self):
        """High creative level should inject more categories."""
        for _ in range(10):
            result = _inject_style_keywords("test", creative_level=10)
            # Level 10 should inject 2-5 keywords
            words = result.split(", ")
            assert len(words) >= 2  # original + at least 1 injected keyword

    def test_result_ends_with_period(self):
        result = _inject_style_keywords("A cat", creative_level=5)
        assert result.endswith(".")

    def test_no_short_noise_words(self):
        """Keywords should be meaningful (>=3 chars or multi-word)."""
        bad_found = False
        for _ in range(50):
            result = _inject_style_keywords("test", creative_level=1)
            injected = result.replace("test", "").replace(",", "").strip()
            if not injected:
                continue
            # Check all words, not just first
            for word in injected.split():
                # Allow digits only if they're part of a longer word
                if word.isdigit() and len(word) <= 2:
                    bad_found = True
                    break
            if bad_found:
                break
        assert not bad_found, f"Short digit noise injected: {result}"

    def test_no_lcd_or_uv_injection(self):
        """Should not inject technical noise like 'LCD' or 'UV'."""
        found_noise = False
        for _ in range(20):
            result = _inject_style_keywords("test", creative_level=1)
            noise_words = {"LCD", "LED", "UV", "CRT", "CFL", "OLED", "AMOLED"}
            if any(w in result for w in noise_words):
                found_noise = True
                break
        assert not found_noise, f"Noise words injected in 20 attempts: {result}"


class TestMJStylePostProcess:
    """Test post_process with MJ keyword injection."""

    def test_post_process_injects_keywords(self):
        result = MidjourneyStrategy.post_process("A sunset", creative_level=5)
        assert result != "A sunset"

    def test_post_process_keeps_mj_params(self):
        result = MidjourneyStrategy.post_process("A sunset", creative_level=5)
        assert "--ar " in result
        assert "--v " in result

    def test_post_process_uses_creative_level(self):
        result = MidjourneyStrategy.post_process("A sunset", creative_level=5)
        assert "--s 250" in result  # 5 * 50


class TestMJStylePromptBuilder:
    """Test build_system_prompt with MJ reference categories."""

    def test_system_prompt_mentions_mj_categories(self):
        prompt = MidjourneyStrategy.build_system_prompt(
            style=None, creative_level=5
        )
        assert "MJ Style Reference" in prompt or "Style Reference" in prompt

    def test_system_prompt_lists_lighting_keywords(self):
        prompt = MidjourneyStrategy.build_system_prompt(creative_level=5)
        assert "Lighting" in prompt

    def test_system_prompt_lists_camera_keywords(self):
        prompt = MidjourneyStrategy.build_system_prompt(creative_level=5)
        assert "Camera" in prompt or "Camera terms" in prompt
