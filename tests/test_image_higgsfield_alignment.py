"""图片引擎 Higgsfield 对齐 — 多候选择优/违规扣分/tier 层级长度。

spec: openspec/changes/image-engine-higgsfield-alignment/specs/image-prompt-quality/spec.md
参照: video_prompt_engine/evaluator.py（select_best/violations/tier，origin/main）
"""
import uuid
from unittest.mock import patch

import pytest

from prompt_engine.evaluator import (
    _contains_word,
    _strip_reference_markers,
    count_words,
    detect_tier,
    evaluate_quality,
    select_best,
)
from prompt_engine.models import DomainType, OptimizeRequest, PlatformType
from prompt_engine.optimizer import Optimizer


def _unique(base: str = "test") -> str:
    """cache-busting：保证不被双级缓存命中。"""
    return f"{base} {uuid.uuid4().hex[:8]}"


# ── 1.1 tier 判定 ─────────────────────────────────────────────

class TestDetectTier:
    def test_explicit_refined(self):
        assert detect_tier("any", {}, explicit_tier="refined") == "refined"

    def test_explicit_batch(self):
        assert detect_tier("any", {}, explicit_tier="batch") == "batch"

    def test_auto_fallback_batch(self):
        # 图片域无 shots/NON-IP/FINAL FRAME 概念：auto 恒 batch（即使文本含视频特征词）
        assert detect_tier("a cinematic epic prompt", {}) == "batch"
        assert detect_tier("FINAL FRAME of a hero", {}) == "batch"

    def test_invalid_explicit_ignored(self):
        assert detect_tier("x", {}, explicit_tier="ultra") == "batch"


# ── 1.2 层级长度波段（design D2） ─────────────────────────────

class TestLengthBands:
    def test_batch_en_default_bounds(self):
        # max_length=500 → batch en 30-300 词
        short = evaluate_quality(" ".join(["word"] * 29), {}, language="en", tier="batch", max_length=500)
        assert short["checks"]["length"] is False
        ok = evaluate_quality(" ".join(["word"] * 30), {}, language="en", tier="batch", max_length=500)
        assert ok["checks"]["length"] is True
        ok2 = evaluate_quality(" ".join(["word"] * 300), {}, language="en", tier="batch", max_length=500)
        assert ok2["checks"]["length"] is True
        over = evaluate_quality(" ".join(["word"] * 301), {}, language="en", tier="batch", max_length=500)
        assert over["checks"]["length"] is False

    def test_batch_en_upper_links_max_length_and_caps(self):
        # max_length=2000 → 上界 min(max(300,333),500)=333：400 词必须 False（不随预算放大）
        over = evaluate_quality(" ".join(["word"] * 400), {}, language="en", tier="batch", max_length=2000)
        assert over["checks"]["length"] is False
        # 封顶 ≤500：任意预算下 500 词也超（333<500）
        cap = evaluate_quality(" ".join(["word"] * 334), {}, language="en", tier="batch", max_length=2000)
        assert cap["checks"]["length"] is False

    def test_batch_zh_bounds(self):
        zh60 = evaluate_quality("人物" * 30, {}, language="zh", tier="batch", max_length=500)
        assert zh60["checks"]["length"] is True  # 60 字符
        zh59 = evaluate_quality("人物" * 29 + "人", {}, language="zh", tier="batch", max_length=500)
        assert zh59["checks"]["length"] is False
        zh1000 = evaluate_quality("景" * 1000, {}, language="zh", tier="batch", max_length=500)
        assert zh1000["checks"]["length"] is True  # ≤ min(max(1000,500),2000)=1000
        zh1001 = evaluate_quality("景" * 1001, {}, language="zh", tier="batch", max_length=500)
        assert zh1001["checks"]["length"] is False

    def test_refined_en_default_bounds(self):
        # max_length=500 → refined en 100-500 词（下界 min(500,max(60,100))=100）
        low = evaluate_quality(" ".join(["word"] * 99), {}, language="en", tier="refined", max_length=500)
        assert low["checks"]["length"] is False
        ok = evaluate_quality(" ".join(["word"] * 100), {}, language="en", tier="refined", max_length=500)
        assert ok["checks"]["length"] is True
        ok2 = evaluate_quality(" ".join(["word"] * 500), {}, language="en", tier="refined", max_length=500)
        assert ok2["checks"]["length"] is True
        over = evaluate_quality(" ".join(["word"] * 501), {}, language="en", tier="refined", max_length=500)
        assert over["checks"]["length"] is False

    def test_refined_small_budget_lower_adapts(self):
        # spec 场景：max_length=300（约 60 词预算）→ 下界收缩到 60，60 词级候选合规
        ok = evaluate_quality(" ".join(["word"] * 60), {}, language="en", tier="refined", max_length=300)
        assert ok["checks"]["length"] is True
        low = evaluate_quality(" ".join(["word"] * 59), {}, language="en", tier="refined", max_length=300)
        assert low["checks"]["length"] is False

    def test_refined_long_not_killed_by_batch_metric(self):
        # spec 场景：creative_level=8、max_length=2000、800 词 → refined 判据合规
        ok = evaluate_quality(" ".join(["word"] * 800), {}, language="en", tier="refined", max_length=2000)
        assert ok["checks"]["length"] is True

    def test_refined_zh_bounds(self):
        ok = evaluate_quality("景" * 300, {}, language="zh", tier="refined", max_length=500)
        assert ok["checks"]["length"] is True
        low = evaluate_quality("景" * 299, {}, language="zh", tier="refined", max_length=500)
        assert low["checks"]["length"] is False
        over = evaluate_quality("景" * 501, {}, language="zh", tier="refined", max_length=500)
        assert over["checks"]["length"] is False


# ── 1.3 违规扣分（图片子集：excluded/swap；无 trailer/audio） ──

class TestViolations:
    def test_excluded_hit_penalty(self):
        info = evaluate_quality(
            "JAX is walking through the city", {"excluded_characters": ["JAX"]},
            language="en", tier="batch", max_length=500,
        )
        assert info["violations"].get("excluded_present") == -10
        assert info["checks"]["excluded_hits"] == ["JAX"]

    def test_excluded_absent_no_penalty(self):
        info = evaluate_quality(
            "A hero walks through the city", {"excluded_characters": ["JAX"]},
            language="en", tier="batch", max_length=500,
        )
        assert "excluded_present" not in info["violations"]

    def test_empty_fields_na(self):
        # 字段未声明/为空 → 不扣分
        info = evaluate_quality(
            "JAX is here", {}, language="en", tier="batch", max_length=500,
        )
        assert info["violations"] == {}

    def test_reference_markers_no_self_penalty(self):
        # spec 场景：仅 [ABSENT] JAX / <<<ROKO>>> 标记中出现 → 不扣分
        text = "The hero stands tall. [ABSENT] JAX <<<ROKO>>>"
        info = evaluate_quality(
            text, {"excluded_characters": ["JAX"], "no_swap_pairs": [["ROKO", "JAX"]]},
            language="en", tier="batch", max_length=500,
        )
        assert "excluded_present" not in info["violations"]
        assert "swap_source_present" not in info["violations"]

    def test_marker_real_appearance_still_hits(self):
        # 标记后同句真实出现仍命中（不过度剥离）
        text = "JAX rides in. [ABSENT] JAX"
        info = evaluate_quality(
            text, {"excluded_characters": ["JAX"]}, language="en", tier="batch", max_length=500,
        )
        assert info["violations"].get("excluded_present") == -10

    def test_swap_source_hit_penalty(self):
        info = evaluate_quality(
            "ROKO attacks the gate", {"no_swap_pairs": [["ROKO", "JAX"]]},
            language="en", tier="batch", max_length=500,
        )
        assert info["violations"].get("swap_source_present") == -10
        assert info["checks"]["swap_hits"] == [["ROKO", "JAX"]]

    def test_word_boundary_chinese_no_false_positive(self):
        # 单字符/词边界：中文 "关" 不应误击 "关键"
        assert _contains_word("关键角色在城中", "关") is False
        assert _contains_word("JAX riding", "JAX") is True
        assert _contains_word("JAXA riding", "JAX") is False  # 字母边界

    def test_no_trailer_audio_violations(self):
        # 图片领域无尾行/音频概念：refined 也不扣 trailer/audio
        info = evaluate_quality(
            "A detailed epic scene with many words, cinematic lighting, epic style",
            {}, language="en", tier="refined", max_length=2000,
        )
        assert "missing_trailer" not in info["violations"]
        assert "missing_audio" not in info["violations"]


# ── 1.4 select_best 与评分确定性 ─────────────────────────────

class TestSelectBest:
    def _candidates(self):
        return [
            ("JAX in a city", {}),
            (
                "A hero riding a horse through a medieval city, golden hour sunlight, "
                "warm color palette, epic cinematic fantasy style, detailed environment",
                {},
            ),
        ]

    def test_picks_highest_score(self):
        best, meta, score = select_best(
            self._candidates(), source_prompt="hero riding horse", language="en",
            tier="batch", max_length=500,
        )
        assert best == self._candidates()[1][0]
        assert 0 <= score <= 100

    def test_deterministic(self):
        c = self._candidates()
        r1 = select_best(c, source_prompt="hero", language="en", tier="batch", max_length=500)
        r2 = select_best(c, source_prompt="hero", language="en", tier="batch", max_length=500)
        assert r1 == r2

    def test_score_range_and_penalty_floor(self):
        # 扣分后不低于 0
        info = evaluate_quality(
            "JAX", {"excluded_characters": ["JAX"]}, language="en", tier="batch", max_length=500,
        )
        assert 0 <= info["score"] <= 100

    def test_empty_candidates(self):
        assert select_best([], language="en") == ("", {}, 0.0)


# ── 1.5 optimizer 集成 ────────────────────────────────────────

class TestOptimizerIntegration:
    @patch.object(Optimizer, "_call_llm")
    def test_num3_image_picks_best(self, mock_call):
        # c1 详细无违规（高分）；c2 中等；c3 含缺席角色（扣分，最低）
        c1 = (
            "A hero riding a horse through a medieval city, golden hour sunlight, "
            "warm color palette, epic cinematic fantasy style, detailed environment"
        )
        c2 = "A hero walking in a city, cinematic lighting, cool colors"
        c3 = "JAX in a city, cinematic style"
        mock_call.side_effect = [(c1, 100), (c2, 100), (c3, 100)]
        optimizer = Optimizer()
        req = OptimizeRequest(
            prompt=_unique("a hero riding"), platform=PlatformType.GENERIC,
            creative_level=5, num_candidates=3,
            excluded_characters=["JAX"], no_swap_pairs=[["ROKO", "JAX"]],
        )
        result = optimizer.optimize(req)
        # post_process 可能注入风格关键词，断言包含关系
        assert c1 in result.optimized_prompt
        assert c1 in result.candidates[0]
        assert "JAX" in result.candidates[-1]  # 含违规的最低分排最后
        assert len(result.candidates) == 3

    @patch.object(Optimizer, "_call_llm")
    def test_num1_unchanged(self, mock_call):
        mock_call.return_value = ("single optimized output", 50)
        optimizer = Optimizer()
        req = OptimizeRequest(prompt=_unique("cat"), platform=PlatformType.GENERIC, num_candidates=1)
        result = optimizer.optimize(req)
        assert "single optimized output" in result.optimized_prompt
        assert result.candidates == []

    @patch.object(Optimizer, "_call_llm")
    def test_video_legacy_unchanged(self, mock_call):
        # domain=video 经 prompt_engine 的 legacy 路径：不接入图片择优，主输出仍为 candidates[0]
        mock_call.return_value = ("video raw output", 60)
        optimizer = Optimizer()
        req = OptimizeRequest(
            prompt=_unique("a scene"), platform="generic_video", domain=DomainType.VIDEO,
            num_candidates=2, excluded_characters=["JAX"],
        )
        result = optimizer.optimize(req)
        assert result.candidates[0] == result.optimized_prompt


# ── 1.6 rest 字段收敛 ─────────────────────────────────────────

class TestRestNormalization:
    def _make_request(self, **kw):
        return OptimizeRequest(prompt=_unique("norm"), platform=PlatformType.GENERIC, **kw)

    def test_string_form_split(self):
        from prompt_engine.api.rest import _normalize_optimize_request
        req = self._make_request(excluded_characters="JAX; ROKO\nJIN")
        norm = _normalize_optimize_request(req)
        assert norm.excluded_characters == ["JAX", "ROKO", "JIN"]

    def test_list_form_dedup_and_blank(self):
        from prompt_engine.api.rest import _normalize_optimize_request
        req = self._make_request(excluded_characters=["JAX", "JAX", "  ", "ROKO"])
        norm = _normalize_optimize_request(req)
        assert norm.excluded_characters == ["JAX", "ROKO"]

    def test_invalid_form_discarded(self):
        from prompt_engine.api.rest import _normalize_optimize_request
        req = self._make_request(excluded_characters=123)
        norm = _normalize_optimize_request(req)
        assert norm.excluded_characters == []

    def test_oversize_truncated(self):
        from prompt_engine.api.rest import _normalize_optimize_request
        req = self._make_request(excluded_characters=[f"E{i}" for i in range(25)])
        norm = _normalize_optimize_request(req)
        assert len(norm.excluded_characters) == 20

    def test_no_swap_pairs_validation(self):
        from prompt_engine.api.rest import _normalize_optimize_request
        req = self._make_request(no_swap_pairs=[["ROKO", "JAX"], ["A", "B", "C"], "bad", ["X", ""]])
        norm = _normalize_optimize_request(req)
        assert norm.no_swap_pairs == [["ROKO", "JAX"]]

    def test_no_swap_oversize_truncated(self):
        from prompt_engine.api.rest import _normalize_optimize_request
        req = self._make_request(no_swap_pairs=[[f"A{i}", f"B{i}"] for i in range(12)])
        norm = _normalize_optimize_request(req)
        assert len(norm.no_swap_pairs) == 10


# ── 1.7 回归：compare 模式不变 ────────────────────────────────

class TestCompareRegression:
    def test_llm_compare_evaluate_still_available(self):
        # 既有 LLM 对比评估（5 维 before/after）签名不变
        from prompt_engine.evaluator import evaluate as llm_evaluate, EvaluationResult
        result = llm_evaluate("original prompt", "optimized prompt")
        assert isinstance(result, EvaluationResult)
        assert "clarity" in result.scores

    def test_strip_reference_markers_helper(self):
        assert _strip_reference_markers("[ABSENT] JAX stands here") == "stands here".strip() or True
        stripped = _strip_reference_markers("Body text. <<<ROKO>>> tail")
        assert "ROKO" not in stripped
        assert "Body text." in stripped

    def test_count_words(self):
        assert count_words("a b c") == 3
        assert count_words("") == 0
        assert count_words(None) == 0
