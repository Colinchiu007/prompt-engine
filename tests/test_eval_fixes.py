"""质量评估修复回归（2026-08-15）：missing_audio/missing_trailer/长度双口径/镜头字段兜底/六要素词表扩充。"""
import pytest

from video_prompt_engine.evaluator import evaluate, select_best


class TestMissingAudioExplicitIntent:
    def test_batch_pure_visual_no_deduction(self):
        r = evaluate("A quiet static wide shot of an empty street at dusk. " * 4, {}, "", "en", tier="batch")
        assert "missing_audio" not in r["violations"]

    def test_batch_explicit_silence_still_deducted(self):
        r = evaluate("无声的画面缓缓展开。 " * 5, {}, "", "zh", tier="batch")
        assert r["violations"].get("missing_audio") == -5

    def test_batch_meta_audio_declared_ok(self):
        r = evaluate("A room interior. " * 5, {"audio": "sfx"}, "", "en", tier="batch")
        assert "missing_audio" not in r["violations"]

    def test_batch_intent_word_ok(self):
        r = evaluate("Epic orchestral score swells. " * 5, {}, "", "en", tier="batch")
        assert "missing_audio" not in r["violations"]

    def test_refined_trailer_audio_unchanged(self):
        r = evaluate("word " * 500 + " Photoreal. NON-IP. 16:9. 8s. music only.",
                     {"audio": "music"}, "", "en", tier="refined", max_length=5000)
        assert "missing_audio" not in r["violations"]


class TestMissingTrailerControlSection:
    def test_duration_aspect_control_section_no_deduction(self):
        r = evaluate("Duration: 12 seconds. Aspect ratio: 16:9. ONE CONTINUOUS SHOT on the hero. " * 8,
                     {}, "", "en", tier="refined", max_length=5000)
        assert "missing_trailer" not in r["violations"]

    def test_plain_refined_no_trailer_deducted(self):
        r = evaluate("A crowd watches the villain arrive. " * 10, {}, "", "en", tier="refined", max_length=5000)
        assert r["violations"].get("missing_trailer") == -10

    def test_non_ip_trailer_still_ok(self):
        r = evaluate("word " * 500 + " Photoreal. NON-IP.", {}, "", "en", tier="refined", max_length=5000)
        assert "missing_trailer" not in r["violations"]


class TestShotFieldTextFallback:
    def test_text_camera_terms_set_flags(self):
        r = evaluate("A slow-motion tracking shot through the city, lens flare, camera tilts up. " * 4,
                     {}, "", "en", tier="batch")
        assert r["checks"]["has_shot"] is True
        assert r["checks"]["has_camera"] is True
        assert r["checks"]["has_motion"] is True

    def test_text_without_camera_terms_flags_false(self):
        r = evaluate("A wooden table with an apple on it. " * 4, {}, "", "en", tier="batch")
        assert r["checks"]["has_shot"] is False
        assert r["checks"]["has_camera"] is False
        assert r["checks"]["has_motion"] is False

    def test_structured_meta_takes_priority(self):
        video = {"shot": {"id": "s1"}, "camera": {"id": "c1"}, "motion_intensity": 0.6}
        r = evaluate("static description without camera words", video, "", "en", tier="batch")
        assert r["checks"]["has_shot"] is True
        assert r["checks"]["has_camera"] is True
        assert r["checks"]["has_motion"] is True


_RICH_SHORT = (
    "A cinematic tracking shot of a warrior charging through a neon city "
    "at dusk with red and gold haze."
)


class TestLengthStrictDualMode:
    # P0-P2 梯度设计（design.md §4）：length_strict=False 评测口径长度带外按接近度得部分分
    # （20 × max(0, 1 - dist/bandwidth)），不再是旧契约的全额 20 或恒差 20/1.2。
    def test_strict_false_length_partial_gradient(self):
        r = evaluate(_RICH_SHORT, {}, "", "en", tier="batch", length_strict=False)
        assert r["checks"]["length"] is False          # 真实判定保留（信息展示）
        assert "length" not in r["violations"]         # 长度不计违规
        assert 0 < r["checks"]["length_points"] < 20   # 带外仍有部分长度分（梯度）
        assert r["score"] >= 60                        # 六要素/镜头字段命中，长度不拉低总分

    def test_strict_true_length_penalty(self):
        lenient = evaluate(_RICH_SHORT, {}, "", "en", tier="batch", length_strict=False)
        strict = evaluate(_RICH_SHORT, {}, "", "en", tier="batch", length_strict=True)
        assert strict["checks"]["length"] is False     # 真实判定仍保留
        assert strict["score"] < lenient["score"]      # 严格口径必须更低
        # 差距 = lenient 的梯度长度分 / 1.2（严格口径 0 分）
        expected_gap = lenient["checks"]["length_points"] / 1.2
        assert abs((lenient["score"] - strict["score"]) - expected_gap) < 0.1  # score 保留 1 位小数

    def test_select_best_accepts_length_strict(self):
        cands = [("a short one", {}), ("A slow-motion tracking shot with lens flare. " * 8, {})]
        best, meta, score = select_best(cands, "", "en", tier="batch", length_strict=True)
        assert score >= 0 and best
        assert "tracking" in best                      # 严格口径下要素更全者胜出


class TestElementKeywordsExpansion:
    def test_style_photography_terms(self):
        r = evaluate("Documentary cinematography with haze and grain. " * 4, {}, "", "en", tier="batch")
        assert r["checks"]["elements"]["style"] is True

    def test_color_concrete_names(self):
        r = evaluate("A red and gold palace under moonlight. " * 4, {}, "", "en", tier="batch")
        assert r["checks"]["elements"]["color"] is True

    def test_subject_robot(self):
        r = evaluate("A white robot mech stands in the snow. " * 4, {}, "", "en", tier="batch")
        assert r["checks"]["elements"]["subject"] is True
