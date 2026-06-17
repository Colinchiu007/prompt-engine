"""反馈存储单元测试"""
import json
import os
import tempfile
from prompt_engine.models import FeedbackEntry, FeedbackStats
from prompt_engine.feedback import FeedbackStore


class TestFeedbackEntry:
    def test_create_feedback_entry(self):
        entry = FeedbackEntry(
            prompt="a cat",
            detected_categories=["lighting", "nature_and_animals"],
            corrected_categories=["lighting"],
            rating=4,
            method="keyword_match",
            confidence=0.85,
        )
        assert entry.prompt == "a cat"
        assert len(entry.detected_categories) == 2
        assert entry.rating == 4

    def test_feedback_stats_model(self):
        stats = FeedbackStats(
            total=10, rated=8, avg_rating=3.5, corrected=3,
            method_breakdown={"keyword_match": 7, "llm_classify": 3},
        )
        assert stats.total == 10
        assert stats.avg_rating == 3.5


class TestFeedbackStore:
    def test_empty_store(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            path = f.name
        try:
            store = FeedbackStore(path)
            assert store.count == 0
            stats = store.stats()
            assert stats.total == 0
            assert stats.rated == 0
        finally:
            os.unlink(path)

    def test_submit_and_retrieve(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            path = f.name
        try:
            store = FeedbackStore(path)
            entry = FeedbackEntry(
                prompt="cyberpunk city",
                detected_categories=["design_styles", "lighting"],
                rating=5,
                method="keyword_match",
                confidence=1.0,
            )
            result = store.submit(entry)
            assert result.id != ""
            assert result.timestamp != ""
            assert store.count == 1

            # Re-load
            store2 = FeedbackStore(path)
            assert store2.count == 1
        finally:
            os.unlink(path)

    def test_stats_with_data(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            path = f.name
        try:
            store = FeedbackStore(path)
            store.submit(FeedbackEntry(prompt="p1", rating=5, method="keyword_match", confidence=1.0))
            store.submit(FeedbackEntry(prompt="p2", rating=3, method="keyword_match", confidence=0.0))
            store.submit(FeedbackEntry(prompt="p3", rating=0, method="llm_classify", confidence=0.0))
            store.submit(FeedbackEntry(
                prompt="p4", rating=4, method="keyword_match", confidence=0.0,
                corrected_categories=["lighting"],
            ))

            stats = store.stats()
            assert stats.total == 4
            assert stats.rated == 3  # p3 has rating=0, not counted
            assert stats.avg_rating == 4.0  # (5+3+4)/3
            assert stats.corrected == 1
            assert stats.method_breakdown["keyword_match"] == 3
            assert stats.method_breakdown["llm_classify"] == 1
        finally:
            os.unlink(path)

    def test_recent_returns_newest_first(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            path = f.name
        try:
            store = FeedbackStore(path)
            for i in range(5):
                store.submit(FeedbackEntry(prompt=f"prompt_{i}", rating=i, method="kw", confidence=0.0))

            recent = store.recent(3)
            assert len(recent) == 3
            # Newest first
            assert recent[0].prompt == "prompt_4"
            assert recent[-1].prompt == "prompt_2"
        finally:
            os.unlink(path)
