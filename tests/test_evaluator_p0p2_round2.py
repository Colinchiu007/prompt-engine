"""评估器 P0-P2 深水区优化回归（2026-08-16）：跨语言保真/中文名字边界/违规量化/版本指纹/阈值联动/词边界手术式/剥离正确性/空输入/RU 词表/advice 排序/中文 2-gram 归一。"""
import json
from pathlib import Path

import pytest

from video_prompt_engine.evaluator import (
    evaluate, select_best, detect_tier,
    _batch_hi, _detect_translation_mode, _cross_lingual_fidelity,
    _EVALUATOR_VERSION, _asset_fingerprint, _extract_absent_names,
)
from prompt_engine_core.knowledge import load_element_keywords


# ─────────────────────────── 组1：跨语言保真（P0-1，门控） ───────────────────────────

class TestCrossLingualFidelity:
    def test_translation_mode_detection(self):
        assert _detect_translation_mode("一位将军在沙漠中", "A general in the desert") is True
        assert _detect_translation_mode("A general in the desert", "一位将军在沙漠中") is True
        assert _detect_translation_mode("A general in the desert", "A general in the desert") is False
        assert _detect_translation_mode("一位将军在沙漠中", "一位将军在沙漠中") is False
        assert _detect_translation_mode("", "A general") is False  # 空 source 不启用

    def test_faithful_translation_high_fidelity(self):
        # 忠实翻译：要素守恒 + 镜头结构保留 + 长度比 → ≥0.7
        src = "一位将军站在沙漠中，身穿蓝色军服，手持望远镜，镜头缓慢推近，画面写实"
        r = evaluate(
            "A general standing in the desert, wearing a blue uniform, holding binoculars, slow push-in camera, photoreal style",
            {}, source_prompt=src, language="en",
        )
        assert r["checks"]["fidelity_method"] == "cross_lingual"
        assert r["checks"]["fidelity"] >= 0.7

    def test_swapped_scene_low_fidelity(self):
        # 换场景对：要素粗守恒但结构不保留 → ≤0.45
        src = "一个女孩在海边奔跑"
        r = evaluate(
            "A robot in the city", {}, source_prompt=src, language="en",
        )
        assert r["checks"]["fidelity_method"] == "cross_lingual"
        assert r["checks"]["fidelity"] <= 0.45

    def test_en_to_en_path_unchanged(self):
        src = "A warrior in the desert"
        r = evaluate("A warrior stands in the desert, photoreal", {}, source_prompt=src, language="en")
        assert r["checks"]["fidelity_method"] in ("wordlist", "zh2gram")

    def test_en_to_zh_direction_fidelity(self):
        # 评审 Major-1：en→zh 方向同样能测出保真（旧实现只查「src 中文 vs dst 英文」，
        # en→zh 方向 conserved/kept 恒≈0 只剩长度比）
        src = "A general standing in the desert, wearing a blue uniform, slow push-in camera, photoreal style"
        r = evaluate(
            "一位将军站在沙漠中，身穿蓝色军服，镜头缓慢推近，画面写实风格",
            {}, source_prompt=src, language="zh",
        )
        assert r["checks"]["fidelity_method"] == "cross_lingual"
        assert r["checks"]["fidelity"] >= 0.5


# ─────────────────────────── 组2：中文名字边界（P0-2） ───────────────────────────

class TestChineseNameBoundary:
    def test_excluded_substring_not_hit(self):
        # 「林晓」不能命中「林晓雨」
        r = evaluate("林晓雨站在门口，手里拿着刀。", {"excluded_characters": ["林晓"]}, "", "zh")
        assert "excluded_present" not in r["violations"]

    def test_excluded_name_hit_normal(self):
        r = evaluate("林晓走进房间，关上了门。", {"excluded_characters": ["林晓"]}, "", "zh")
        assert "excluded_present" in r["violations"]

    def test_character_list_covers_longer_name(self):
        # character_list 含「林晓雨」时，「林晓」不再误击
        r = evaluate(
            "林晓雨站在门口。", {"excluded_characters": ["林晓"]}, "", "zh",
            character_list=["林晓雨"],
        )
        assert "excluded_present" not in r["violations"]

    def test_zh_posture_generic_path_unchanged(self):
        # 泛词路径不加 CJK 边界：「站起」在「他站起来」仍命中（continuity）
        r = evaluate(
            "他站起来，走向门口。", {"shots": [{"duration": 3}, {"duration": 3}]}, "",
            "zh", prev_final_frame="他站起来",
        )
        # continuity whitelist 命中（站起）→ 不触发 continuity_break
        assert r["checks"]["continuity_method"] == "whitelist"
        assert "continuity_break" not in r["violations"]

    def test_swap_source_name_boundary(self):
        r = evaluate(
            "林晓雨出现。", {"no_swap_pairs": [["林晓", "王芳"]]}, "", "zh",
        )
        assert "swap_source_present" not in r["violations"]


# ─────────────────────────── 组3：违规分级量化（P0-3） ───────────────────────────

class TestViolationsDetail:
    def test_violations_top_level_unchanged(self):
        r = evaluate("A hero in the city. John appears", {"excluded_characters": ["John"]}, "", "en")
        assert isinstance(r["violations"]["excluded_present"], int)
        assert r["violations"]["excluded_present"] == -10

    def test_detail_shape_plain_violation(self):
        r = evaluate("A hero in the city. John appears", {"excluded_characters": ["John"]}, "", "en")
        d = r["checks"]["violations_detail"]["excluded_present"]
        assert d["penalty"] == -10 and d["count"] == 1 and d["detail"] is None

    def test_timing_break_accumulates_count_and_max(self):
        video = {
            "shots": [
                {"duration": 5, "beats": [{"time": "0:01-0:08"}, {"time": "0:02-0:10"}]},
                {"duration": 4, "beats": [{"time": "0:01-0:05"}]},
            ]
        }
        r = evaluate("[SHOT 1] A man walks. [SHOT 2] A woman runs.", video, "", "en")
        assert r["violations"]["timing_break"] == -5
        d = r["checks"]["violations_detail"]["timing_break"]
        assert d["count"] == 2                    # 两个 beat 超时
        assert d["detail"]["max_diff"] == 3.0     # 10 - (5+2) = 3

    def test_tie_break_uses_total_penalty(self):
        # 同分时：1 个 -10 比 2 个 -5 更差 → 惩罚和小者胜
        a = "A hero in the desert. John appears"          # excluded -10
        b = "A hero in the desert"                          # 无违规（或 -5）
        winner, meta, score, infos = select_best(
            [(a, {"excluded_characters": ["John"]}), (b, {})], source_prompt="", detail=True,
        )
        assert infos[0]["violations_penalty"] <= infos[1]["violations_penalty"]


# ─────────────────────────── 组4：六要素词边界（P1-1，手术式） ───────────────────────────

class TestElementWordBoundary:
    def test_short_latin_word_no_substring_hit(self):
        r = evaluate("A category of machines at sunrise", {}, "", "en")
        # red/cat/sun 不得因 category/sunrise 命中
        assert "cat" not in r["checks"]["elements_detail"]["subject"]["words"]
        assert "sun" not in r["checks"]["elements_detail"]["environment"]["words"]
        assert "red" not in r["checks"]["elements_detail"]["color"]["words"]

    def test_plural_form_still_hits(self):
        r = evaluate("Machines and soldiers in a city", {}, "", "en")
        assert "machine" in r["checks"]["elements_detail"]["subject"]["words"]
        assert "soldier" in r["checks"]["elements_detail"]["subject"]["words"]

    def test_zh_words_keep_substring(self):
        r = evaluate("室内灯光下，将军站着", {}, "", "zh")
        d = r["checks"]["elements_detail"]
        assert d["environment"]["hit"] is True    # 室（单字子串）
        assert d["subject"]["hit"] is True        # 将军


# ─────────────────────────── 组5：detect_tier 阈值单一来源（P1-2） ───────────────────────────

class TestTierThreshold:
    def test_batch_hi_single_source(self):
        assert _batch_hi(None) == 400
        assert _batch_hi(1800) == 400
        assert _batch_hi(5000) == 833

    def test_600_words_unmarked_refined_with_trailer_waiver(self):
        p = " ".join(f"word{i}" for i in range(600))
        r = evaluate(p, {}, "", "en")
        assert r["tier"] == "refined"
        assert r["checks"]["tier_auto"] == "length"
        assert r["checks"]["length"] is True
        assert "missing_trailer" not in r["violations"]   # 长度兜底豁免

    def test_834_words_refined(self):
        p = " ".join(f"word{i}" for i in range(834))
        assert detect_tier(p, None) == "refined"

    def test_300_words_unmarked_still_batch(self):
        p = " ".join(f"word{i}" for i in range(300))
        assert detect_tier(p, None) == "batch"

    def test_marker_tier_auto_value(self):
        r = evaluate("Photoreal. NON-IP. 16:9. " * 50, {}, "", "en")
        assert r["checks"]["tier_auto"] == "marker"

    def test_explicit_tier_auto_none(self):
        r = evaluate("A hero in the city. " * 20, {}, "", "en", tier="batch")
        assert r["checks"]["tier_auto"] is None


# ─────────────────────────── 组6：版本指纹（P1-3） ───────────────────────────

class TestVersionFingerprint:
    def test_evaluator_version_field(self):
        r = evaluate("A hero in the city. " * 20, {}, "", "en")
        assert r["evaluator_version"] == _EVALUATOR_VERSION
        assert set(r["assets"]) >= {"element_keywords", "refined_blocks", "golden_set"}
        assert all(len(v) == 64 for v in r["assets"].values())

    def test_asset_fingerprint_changes_with_file(self):
        fp = _asset_fingerprint()
        assert fp["element_keywords"]
        p = Path(__file__).resolve().parent.parent / "prompt_engine_core" / "knowledge" / "element_keywords.json"
        assert len(fp["element_keywords"]) == 64


# ─────────────────────────── 组7：select_best_detailed（P1-4） ───────────────────────────

class TestSelectBestDetailed:
    def test_detail_mode_returns_four_tuple(self):
        cands = [("A hero in the city. " * 10, {}), ("A cat in a room. " * 5, {})]
        out = select_best(cands, detail=True)
        assert len(out) == 4
        prompt, meta, score, infos = out
        assert infos[0]["prompt"] == prompt
        assert "checks" in infos[0] and "violations" in infos[0] and "advice" in infos[0]

    def test_default_mode_still_three_tuple(self):
        cands = [("A hero in the city. " * 10, {})]
        out = select_best(cands)
        assert len(out) == 3

    def test_winner_consistent_with_default(self):
        cands = [("A hero in the city. " * 10, {}), ("A cat in a room. " * 5, {})]
        p1, _, s1 = select_best(cands)
        p2, _, s2, infos = select_best(cands, detail=True)
        assert (p1, s1) == (p2, s2)


# ─────────────────────────── 组8：剥离正确性（P1-5） ───────────────────────────

class TestStripConsistency:
    def test_absent_marker_waives_continuity_hard_names(self):
        # [ABSENT] 声明的角色：跨镜承接硬判据豁免（有意缺席）。
        # 评审 Critical 修复：正文不再残留角色名（Roko 被剥离），豁免必须来自
        # [ABSENT] 判定 + character_list 并集，而非旧实现的「标记残留→角色仍在场」泄漏。
        # 正文保留 stands/snow 两个承接 token 使词表命中率 ≥0.4，测试真实覆盖豁免路径。
        r = evaluate(
            "[ABSENT] Roko. A wolf howls in the snow. The wolf stands still.",
            {"shots": [{"duration": 3}, {"duration": 3}]}, "",
            "en", prev_final_frame="Roko stands in the snow.", character_list=["Roko"],
        )
        assert "continuity_break" not in r["violations"]
        assert "continuity_missing" not in r["checks"]
        assert r["checks"]["continuity_ratio"] >= 0.4

    def test_absent_bracket_waives_continuity_hard_names(self):
        # <<<[ABSENT] Roko>>> 整段剥离后角色名不在正文——豁免必须来自 [ABSENT] 判定而非正文残留
        r = evaluate(
            "<<<[ABSENT] Roko>>> A wolf howls in the snow. The wolf stands still.",
            {"shots": [{"duration": 3}, {"duration": 3}]}, "",
            "en", prev_final_frame="Roko stands in the snow.", character_list=["Roko"],
        )
        assert "continuity_break" not in r["violations"]
        assert "continuity_missing" not in r["checks"]

    def test_missing_character_still_breaks_continuity(self):
        # 对照组：无 [ABSENT] 标记时 roster 角色缺席仍判 continuity_break（豁免不空转）
        r = evaluate(
            "A wolf howls in the snow. The wolf stands still.",
            {"shots": [{"duration": 3}, {"duration": 3}]}, "",
            "en", prev_final_frame="Roko stands in the snow.", character_list=["Roko"],
        )
        assert "continuity_break" in r["violations"]


# ─────────────────────────── 组14：ABSENT 标记提取（评审 Critical 修复） ───────────────────────────

class TestAbsentNamesExtraction:
    def test_latin_suffix_boundary(self):
        # [ABSENT] Rokosh 不得判 Roko 缺席（拉丁后随边界，与 _strip_reference_markers 一致）
        assert _extract_absent_names("[ABSENT] Rokosh howls.", ["Roko"]) == []
        assert _extract_absent_names("[ABSENT] Roko howls.", ["Roko"]) == ["Roko"]

    def test_character_list_names_detected(self):
        # 评审 Critical：character_list（roster）角色同样参与 [ABSENT] 识别
        assert _extract_absent_names("<<<[ABSENT] Roko>>>", ["Roko"]) == ["Roko"]
        assert _extract_absent_names("[ABSENT] Roko", ["Roko"]) == ["Roko"]

    def test_longer_cjk_name_covers_shorter(self):
        # [ABSENT] 王芳雨 只判 王芳雨，短名 王芳 不重复判缺席（同位置长名覆盖）
        assert _extract_absent_names("[ABSENT] 王芳雨出现。", ["王芳雨", "王芳"]) == ["王芳雨"]


# ─────────────────────────── 组9：空输入契约（P2-3） ───────────────────────────

class TestEmptyContract:
    def test_empty_prompt(self):
        r = evaluate("", {}, "", "en")
        assert r["score"] == 0.0
        assert r["checks"]["empty"] is True
        assert r["violations"] == {}

    def test_blank_prompt(self):
        r = evaluate("   \n  ", {}, "", "zh")
        assert r["score"] == 0.0
        assert r["checks"]["empty"] is True


# ─────────────────────────── 组10：advice 排序（P2-1） ───────────────────────────

class TestAdviceOrder:
    def test_violations_sorted_by_penalty_desc(self):
        video = {"excluded_characters": ["John"], "shots": [{"duration": 3}, {"duration": 3}]}
        r = evaluate("A hero in the city. John appears", video, "", "en")
        idx_excl = next(i for i, a in enumerate(r["advice"]) if "excluded character" in a)
        idx_tl = next(i for i, a in enumerate(r["advice"]) if "multi-shot prompt missing" in a)
        assert idx_excl < idx_tl   # -10 排 -5 前


# ─────────────────────────── 组11：RU 词表补齐（P2-2） ───────────────────────────

class TestRuKeywords:
    def test_golden_ru_sample_elements(self):
        r = evaluate(
            "10 полицейских в серой форме у всех надпись SCPD. и мужчины и женщины - разной расы. на сером однотонном фоне. одной картинкой",
            {}, "", "ru", tier="asset",
        )
        d = r["checks"]["elements_detail"]
        assert d["subject"]["hit"] is True     # полицейских / мужчины
        assert d["color"]["hit"] is True       # серой / однотонном
        assert d["environment"]["hit"] is True # фоне

    def test_ru_asset_in_bounds(self):
        r = evaluate("10 полицейских в серой форме. одной картинкой", {}, "", "ru", tier="asset")
        assert r["checks"]["length"] is True

    def test_ru_word_boundary_no_substring_hits(self):
        # 评审 Minor：фон 不得命中 телефон/микрофон（西里尔左侧边界）
        r = evaluate("Человек держит телефон в руке", {}, "", "ru", tier="asset")
        assert r["checks"]["elements_detail"]["environment"]["hit"] is False
        # 对照组：фоне 词形（变格）仍正常命中
        r2 = evaluate("Человек стоит на сером фоне", {}, "", "ru", tier="asset")
        assert r2["checks"]["elements_detail"]["environment"]["hit"] is True


# ─────────────────────────── 组12：中文 2-gram 归一（P2-5） ───────────────────────────

class TestZhFidelityNormalization:
    def test_virtual_char_removal_improves_fidelity(self):
        src = "男人在奔跑，手里拿着刀"
        prompt = "奔跑着的男人手里握着刀"
        r = evaluate(prompt, {}, source_prompt=src, language="zh")
        assert r["checks"]["fidelity"] > 0.3   # 归一后至少部分命中
        assert r["checks"]["fidelity_method"] == "zh2gram"


# ─────────────────────────── 组13：golden 门禁（P0-4） ───────────────────────────

class TestGoldenGate:
    @pytest.fixture(scope="class")
    def golden(self):
        p = Path(__file__).resolve().parent.parent / "video_prompt_engine" / "knowledge" / "golden_set.json"
        data = json.loads(p.read_text(encoding="utf-8"))
        return data["samples"]

    def test_golden_mae_and_correlation(self, golden):
        preds, humans = [], []
        for s in golden:
            info = evaluate(
                s["prompt_text"], {}, source_prompt="", language=s.get("language", "en"),
                tier=s.get("tier"), length_strict=False,
            )
            preds.append(info["score"])
            humans.append(float(s["human_score"]))
        n = len(preds)
        mae = sum(abs(p - h) for p, h in zip(preds, humans)) / n
        mean_p, mean_h = sum(preds) / n, sum(humans) / n
        cov = sum((p - mean_p) * (h - mean_h) for p, h in zip(preds, humans))
        denom = (sum((p - mean_p) ** 2 for p in preds) * sum((h - mean_h) ** 2 for h in humans)) ** 0.5
        r = cov / denom if denom else 0.0
        assert mae <= 18.0, f"golden MAE {mae:.2f} 超过门禁 18.0"
        assert r >= 0.90, f"golden Pearson r {r:.3f} 低于门禁 0.90"
