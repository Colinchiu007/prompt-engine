"""评估器 round3 回归（2026-08-16）：zh/ru 长度兜底 / CJK 合成词词表 v3 / 258 哨兵门禁 / 正则缓存 / 镜头分型 instrumentation / 无 source 缩放封顶。"""
import json
from pathlib import Path

import pytest

from video_prompt_engine.evaluator import (
    evaluate, detect_tier, _EVALUATOR_VERSION,
    _WORD_BOUNDARY_RE, _TYPE_NEGATION_RE,
    _SHOT_TYPE_WORDS, _MOT_TYPE_WORDS, _collect_types,
)
from scripts.eval_corpus_258 import compute_metrics, check_gate, detect_lang
from prompt_engine_core.knowledge import load_element_keywords


# ─────────────────────────── 组1：zh/ru 字符刻度长度兜底（P0-1） ───────────────────────────

class TestZhRuLengthFallback:
    def test_zh_2500_unmarked_refined(self):
        assert detect_tier("中" * 2500, {}, language="zh") == "refined"

    def test_zh_1900_still_batch(self):
        assert detect_tier("中" * 1900, {}, language="zh") == "batch"

    def test_ru_2500_unmarked_refined(self):
        assert detect_tier("р" * 2500, {}, language="ru") == "refined"

    def test_en_default_backward_compatible(self):
        # language 默认 en：词数兜底行为不变（834 词 → refined）
        p = " ".join(f"word{i}" for i in range(834))
        assert detect_tier(p, None) == "refined"

    def test_zh_length_fallback_waives_trailer(self):
        r = evaluate("中" * 2500, {}, "", "zh")
        assert r["tier"] == "refined"
        assert r["checks"]["tier_auto"] == "length"
        assert "missing_trailer" not in r["violations"]

    def test_zh_refined_audio_intent_no_missing_audio(self):
        # 中文精修带音频意图词 → 不再恒 -5（Round3 P0-1 耦合修）
        r = evaluate("一位将军站在沙漠中，音效丰富，配乐激昂。", {}, "", "zh", tier="refined")
        assert "missing_audio" not in r["violations"]

    def test_zh_refined_without_audio_still_penalized(self):
        r = evaluate("一位将军站在沙漠中，风沙漫天。", {}, "", "zh", tier="refined")
        assert "missing_audio" in r["violations"]


# ─────────────────────────── 组2：CJK 合成词词表 v3（P0-2） ───────────────────────────

class TestCjkVocabV3:
    def test_vocab_version_3(self):
        kw, _ = load_element_keywords()
        path = Path(__file__).resolve().parent.parent / "prompt_engine_core" / "knowledge" / "element_keywords.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["version"] == 3
        assert "人物" in kw["subject"]["zh"]
        assert "奔跑" in kw["action"]["zh"]

    def test_single_char_mis_hits_removed(self):
        # 角色/曝光/时光/金属/绝望/战术 均为单字误击案例，v3 后必须零命中
        r = evaluate("角色在曝光时光里看着金属战术背包", {}, "", "zh", tier="batch")
        d = r["checks"]["elements_detail"]
        assert d["color"]["hit"] is False       # 色 → 角色
        assert d["lighting"]["hit"] is False    # 光 → 曝光/时光
        assert d["action"]["hit"] is False      # 战 → 战术 / 望 → 绝望
        assert d["environment"]["hit"] is False

    def test_scene_words_not_environment(self):
        r = evaluate("中景与远景切换", {}, "", "zh", tier="batch")
        assert r["checks"]["elements_detail"]["environment"]["hit"] is False

    def test_compound_words_still_hit(self):
        r = evaluate("室内灯光下，将军站着，红色轿车在奔跑", {}, "", "zh", tier="batch")
        d = r["checks"]["elements_detail"]
        assert d["subject"]["hit"] is True          # 将军
        assert d["environment"]["hit"] is True      # 室内
        assert d["lighting"]["hit"] is True         # 灯光
        assert d["action"]["hit"] is True           # 站着/奔跑
        assert d["color"]["hit"] is True            # 红色

    def test_subject_single_char_ren_exception(self):
        # subject 保留「人」为刻意例外（四人/每人/有人 真实主体）
        r = evaluate("四个人站在门口", {}, "", "zh", tier="batch")
        assert r["checks"]["elements_detail"]["subject"]["hit"] is True

    def test_round2_zh_test_semantics_kept(self):
        # round2 同文案：环境/主体命中语义从单字升级为合成词，断言不破
        r = evaluate("室内灯光下，将军站着", {}, "", "zh")
        d = r["checks"]["elements_detail"]
        assert d["environment"]["hit"] is True
        assert d["subject"]["hit"] is True


# ─────────────────────────── 组3：258 哨兵门禁（P0-3） ───────────────────────────

class TestCorpus258Sentinel:
    def test_detect_lang_three_way(self):
        assert detect_lang("一位将军在沙漠") == "zh"
        assert detect_lang("Полицейский в городе") == "ru"
        assert detect_lang("A general in the desert") == "en"

    def test_compute_metrics_smoke(self):
        items = [
            {"prompt_text": "A hero in a ruined city with neon light. " * 6},
            {"prompt_text": "一位将军在沙漠中奔跑"},
        ]
        m = compute_metrics(items)
        assert m["n"] == 2
        assert 0 <= m["mean"] <= 100
        assert m["ge90"] + m["lt60"] <= 2

    def test_gate_rejects_regression(self):
        # 注入回归（全低分）→ 门禁必须失败
        items = [{"prompt_text": "cat"} for _ in range(258)]
        m = compute_metrics(items, evaluate_fn=lambda *a, **k: {"score": 10.0, "violations": {}})
        assert check_gate(m), "全低分注入必须被哨兵拦截"

    def test_gate_rejects_wrong_total(self):
        m = {"n": 257, "mean": 95.0, "median": 96.0, "ge90": 250, "ge80": 257, "lt60": 0, "missing_audio": 0}
        assert check_gate(m)  # n != 258 硬断言

    def test_gate_passes_healthy_baseline(self):
        m = {"n": 258, "mean": 92.3, "median": 98.0, "ge90": 213, "ge80": 221, "lt60": 20, "missing_audio": 25}
        assert check_gate(m) == []


# ─────────────────────────── 组4：正则缓存（P1-1） ───────────────────────────

class TestRegexCache:
    def test_word_boundary_cache_hits_and_bounded(self):
        _WORD_BOUNDARY_RE.cache_clear()
        evaluate("A hero in the city. " * 20, {}, "", "en")
        info = _WORD_BOUNDARY_RE.cache_info()
        assert info.hits > 0
        assert info.currsize <= 2048

    def test_negation_re_cached(self):
        _TYPE_NEGATION_RE.cache_clear()
        evaluate("no rotation, camera static", {})
        assert _TYPE_NEGATION_RE.cache_info().currsize <= 2048


# ─────────────────────────── 组5：镜头分型 instrumentation（P1-2） ───────────────────────────

class TestShotTypeInstrumentation:
    def test_shot_types_extraction(self):
        r = evaluate("Wide close-up of a man", {}, "", "en")
        assert r["checks"]["shot_types"] == ["wide", "closeup"]
        assert r["checks"]["shot_type_count"] == 2

    def test_structural_shot_no_type(self):
        r = evaluate("a shot of a cat", {}, "", "en")
        assert r["checks"]["shot_types"] == []
        assert r["checks"]["shot_type_count"] == 0
        assert r["checks"]["has_shot"] is True

    def test_motion_negation(self):
        r = evaluate("no rotation, camera static", {}, "", "en")
        assert r["checks"]["motion_types"] == []          # no rotation 否定感知
        assert r["checks"]["camera_types"] == ["cam_position"]

    def test_motion_types_positive(self):
        r = evaluate("slow pan with zoom and crane", {}, "", "en")
        assert set(r["checks"]["motion_types"]) == {"pan", "zoom", "crane"}

    def test_zh_motion_and_negation(self):
        r = evaluate("镜头缓慢推近", {}, "", "zh")
        assert "zoom" in r["checks"]["motion_types"]
        r2 = evaluate("无旋转，固定机位", {}, "", "zh")
        assert r2["checks"]["motion_types"] == []
        assert r2["checks"]["shot_types"] == ["static"]

    def test_motion_words_not_shot_types(self):
        # 纯运镜型（pan/zoom/crane…）归 motion 不归 shot（tracking/dolly 是景别型特例，设计保留双侧）
        r = evaluate("slow pan with zoom and crane", {}, "", "en")
        assert r["checks"]["shot_types"] == []
        assert set(r["checks"]["motion_types"]) == {"pan", "zoom", "crane"}

    def test_camera_types_lens(self):
        r = evaluate("35mm lens, low angle", {}, "", "en")
        assert "lens_optics" in r["checks"]["camera_types"]

    def test_empty_contract_shape_aligned(self):
        r = evaluate("", {}, "", "en")
        assert r["checks"]["shot_types"] == []
        assert r["checks"]["shot_type_count"] == 0
        assert r["checks"]["motion_types"] == []


# ─────────────────────────── 组6：无 source 缩放封顶（P2-1） ───────────────────────────

def _full_elements_prompt() -> str:
    # 六要素每要素 ≥3 词 → elements_score=1.0；asset 带长度 OK + 三镜头布尔全中
    return (
        "a man and a woman with a girl and a boy, walking and running and dancing, "
        "in a forest and a city on a street, with light and glow and neon and moonlight, "
        "red and blue and black and white colors, cinematic noir photoreal style, "
        "wide shot, camera pan, slow motion"
    )


class TestNoSourceCap:
    def test_no_source_capped_at_97(self):
        r = evaluate(_full_elements_prompt(), {}, "", "en", tier="asset", length_strict=False)
        assert r["checks"]["elements_score"] == pytest.approx(1.0, abs=0.01)
        assert r["score"] <= 97.0

    def test_scaled_cap_below_97(self):
        # elements_score=0.833 → ceiling = 90 + 7*0.833 = 95.8
        r = evaluate(
            "a man in a forest with red and blue colors, cinematic style, wide shot, camera pan, slow motion",
            {}, "", "en", tier="asset", length_strict=False,
        )
        cap = 90 + 7 * r["checks"]["elements_score"]
        assert r["score"] <= cap + 1e-9

    def test_with_source_can_reach_100(self):
        src = _full_elements_prompt()
        r = evaluate(src, {}, source_prompt=src, language="en", tier="asset", length_strict=False)
        assert r["checks"]["fidelity"] == 1.0
        assert r["score"] == 100.0

    def test_short_card_not_artificially_lowered(self):
        # 短卡（低要素覆盖）floor：无 source 封顶不得把低分样本进一步压低
        r = evaluate("cat", {}, "", "en", tier="asset", length_strict=False)
        assert r["score"] >= 0
        assert r["score"] <= 90 + 7 * r["checks"]["elements_score"] + 1e-9


# ─────────────────────────── 组7：版本指纹 ───────────────────────────

class TestVersionBump:
    def test_version_v012(self):
        assert _EVALUATOR_VERSION == "v0.12-deterministic"
        r = evaluate("A hero in the city. " * 20, {}, "", "en")
        assert r["evaluator_version"] == "v0.12-deterministic"
