"""评估器 round3 回归（2026-08-16）：zh/ru 长度兜底 / CJK 合成词词表 v3 / 258 哨兵门禁 / 正则缓存 / 镜头分型 instrumentation / 无 source 缩放封顶。"""
import json
from pathlib import Path

import pytest

from video_prompt_engine.evaluator import (
    evaluate, detect_tier, detect_lang, _EVALUATOR_VERSION,
    _WORD_BOUNDARY_RE,
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
    def test_vocab_version_4(self):
        kw, _ = load_element_keywords()
        path = Path(__file__).resolve().parent.parent / "prompt_engine_core" / "knowledge" / "element_keywords.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["version"] == 4  # v4：评审 W2 补 zh 动作高频形态（走着/跑来/挥手…）
        assert "人物" in kw["subject"]["zh"]
        assert "奔跑" in kw["action"]["zh"]
        assert "走着" in kw["action"]["zh"]

    def test_single_char_mis_hits_removed(self):
        # 角色/曝光/时光/金属/战术 均为单字误击案例，v3 去单字后必须零命中
        r = evaluate("角色在曝光时光里的金属战术背包", {}, "", "zh", tier="batch")
        d = r["checks"]["elements_detail"]
        assert d["color"]["hit"] is False       # 色 → 角色
        assert d["lighting"]["hit"] is False    # 光 → 曝光/时光
        assert d["action"]["hit"] is False      # 战 → 战术（单字误击）
        assert d["environment"]["hit"] is False

    def test_action_inflected_forms_recalled(self):
        # 评审 W2：v4 补高频动作形态（走着/跑来/挥手…），子串命中恢复召回
        r = evaluate("将军走着，小孩跑来，挥手告别", {}, "", "zh", tier="batch")
        d = r["checks"]["elements_detail"]
        assert d["action"]["hit"] is True
        assert d["action"]["words"] == ["走着", "跑来", "挥手"]

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

    def test_word_boundary_cache_bounded_after_multiple_evaluations(self):
        # 评审 W1：_TYPE_NEGATION_RE 已删除（分句否定复用 _occurrence_is_negated），
        # 缓存有界性由 _WORD_BOUNDARY_RE 覆盖（动态 token 场景不无界膨胀）
        _WORD_BOUNDARY_RE.cache_clear()
        for i in range(50):
            evaluate(f"token_{i} moves and fights, no camera pan", {}, "", "en")
        assert _WORD_BOUNDARY_RE.cache_info().currsize <= 2048


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

    def test_motion_negation_clause_scoped(self):
        # 评审 W1：否定按分句全出现语义——前半正向不得被后半否定整体抑制
        r = evaluate("tracking shot, but no tracking in the second half", {}, "", "en")
        assert "tracking" in r["checks"]["shot_types"]
        assert "track" in r["checks"]["motion_types"]
        r2 = evaluate("no rotation, camera static", {}, "", "en")
        assert r2["checks"]["motion_types"] == []

    def test_zh_negation_clause_scoped(self):
        # 评审 W1：中文混合语境同样按分句判定（"不要摇镜，但前半有正向"）
        r = evaluate("先缓慢推近，不要摇镜", {}, "", "zh")
        assert "zoom" in r["checks"]["motion_types"]
        r2 = evaluate("不要摇镜", {}, "", "zh")
        assert "pan" not in r2["checks"]["motion_types"]

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
        # 评审 I2：五要素满分 + 一要素缺失 → elements_score=5/6，主公式恰好触达 ceiling
        # （raw = (20+25+20+15+15+20)/1.2 = 95.83 == 90+7*(5/6)），断言封顶真实绑定
        r = evaluate(
            "a man with a woman and a boy, walking and running and dancing, "
            "in a forest in a city on a street, with bright light and glow and moonlight, "
            "red and blue and black colors, wide shot, camera pan, slow motion",
            {}, "", "en", tier="asset", length_strict=False,
        )
        assert r["checks"]["elements_score"] == pytest.approx(5 / 6, abs=0.01)
        assert r["score"] == pytest.approx(90 + 7 * (5 / 6), abs=0.1)

    def test_with_source_can_reach_100(self):
        src = _full_elements_prompt()
        r = evaluate(src, {}, source_prompt=src, language="en", tier="asset", length_strict=False)
        assert r["checks"]["fidelity"] == 1.0
        assert r["score"] == 100.0

    def test_short_card_floor_snapshots(self):
        # 评审 I3：短卡地板快照（P2-1 核心保证）——无 source 缩放封顶不得压低低分短卡；
        # 口径与 scripts/eval_golden_set.py 一致（样本声明 tier/language，length_strict=False），
        # 实测 2026-08-16 v0.12：43.1/44.4/55.6/39.7
        expected = {
            "hg-credits-013": 43.1,
            "hg-scene_cinema_bomb-003": 44.4,
            "hg-assets-020": 55.6,
            "hg-credits-016": 39.7,
        }
        gpath = Path(__file__).resolve().parent.parent / "video_prompt_engine" / "knowledge" / "golden_set.json"
        samples = {s["id"]: s for s in json.loads(gpath.read_text(encoding="utf-8"))["samples"]}
        for sid, floor in expected.items():
            s = samples[sid]
            r = evaluate(
                s["prompt_text"], {}, source_prompt="",
                language=s.get("language", "en"), tier=s.get("tier"), length_strict=False,
            )
            assert r["score"] == pytest.approx(floor, abs=0.15), f"{sid} floor collapsed: {r['score']} != {floor}"


# ─────────────────────────── 组7：评审修复回归（W1/W3/W4/W5） ───────────────────────────

class TestReviewFixes:
    def test_refined_dialogue_audio_intent(self):
        # 评审 W3：refined/batch 音频意图词统一单表——en dialogue/voiceover/narration 不再误扣
        for prompt in (
            "A cinematic shot with dialogue",
            "A slow scene with voiceover narration",
        ):
            r = evaluate(prompt, {}, "", "en", tier="refined")
            assert "missing_audio" not in r["violations"], prompt
        # zh 音频意图词（round3 P0-1 延续）与 ru 主格词同样生效
        assert "missing_audio" not in evaluate("安静的镜头，只有风声", {}, "", "zh", tier="refined")["violations"]
        assert "missing_audio" not in evaluate("Тихая сцена, музыка и голос", {}, "", "ru", tier="refined")["violations"]

    def test_language_normalized_case_and_variant(self):
        # 评审 W5：language 入口归一化（zh-CN→zh、ZH→zh），长度兜底与分带口径一致
        assert detect_tier("中" * 2500, {}, language="zh-CN") == "refined"
        assert detect_tier("中" * 2500, {}, language="ZH") == "refined"
        r = evaluate("中" * 2500, {}, "", "zh-CN")
        assert r["tier"] == "refined"
        assert r["checks"]["length_band"] == [500, 5000]   # refined zh 分带
        rb = evaluate("中" * 1000, {}, "", "zh-CN")
        assert rb["tier"] == "batch"
        assert rb["checks"]["length_band"] == [120, 2000]  # batch zh 分带（W6 常量）

    def test_api_language_auto_detect(self):
        # 评审 W4：/v1/video/evaluate 未显式传 language 时按正文自动判定（与哨兵同一 detect_lang）
        assert detect_lang("中文提示词") == "zh"
        assert detect_lang("русский сценарий") == "ru"
        assert detect_lang("english prompt") == "en"

    def test_char_batch_hi_single_source(self):
        # 评审 W6：zh/ru batch 上界单一来源——1900 字仍在带内、2001 字兜底 refined
        assert detect_tier("中" * 1900, {}, language="zh") == "batch"
        assert detect_tier("中" * 2001, {}, language="zh") == "refined"
        r = evaluate("中" * 1900, {}, "", "zh")
        assert r["checks"]["length_band"][1] == 2000


# ─────────────────────────── 组8：版本指纹 ───────────────────────────

class TestVersionBump:
    def test_version_v012(self):
        assert _EVALUATOR_VERSION == "v0.12-deterministic"
        r = evaluate("A hero in the city. " * 20, {}, "", "en")
        assert r["evaluator_version"] == "v0.12-deterministic"
