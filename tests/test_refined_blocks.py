"""Round3 Batch C — refined 块骨架 / 覆盖度 / lock-gated 启发式回归测试。

覆盖（评审修订版）：
- T2 _clean_blocks：键白名单/非字符串丢弃/截断 4000/空 → None
- T4 render 骨架化：blocks 优先/缺失块回退/零回归/内嵌尾行剥离/batch 不启用
- C6 交互：strip_rendered_trailer 末位匹配，blocks 中段 Photoreal NON-IP 不误剥
- T5 block_coverage：refined 自渲染口径；batch 不启用
- gated：enabled_rules 生效/否定感知/未启用规则不触发
- T6 盐 V4
"""
from __future__ import annotations

import json
from pathlib import Path

from video_prompt_engine.strategies.base import (
    BaseVideoStrategy, _clean_blocks, _BLOCKS_ORDER,
)
from video_prompt_engine.refined_blocks import strip_embedded_trailer as _strip_embedded_trailer
from video_prompt_engine.optimizer import VideoOptimizer, fit_refined_trailer, strip_rendered_trailer
from video_prompt_engine.evaluator import _negated, evaluate
from video_prompt_engine.models import VideoOptimizeRequest, VideoPromptMeta

REFINED = "refined"
BATCH = "batch"

BLOCKS_SAMPLE = {
    "SCENE NOTE": "The end. Roko kneels over Jax in heavy blizzard.",
    "SPATIAL LAYOUT": "Cold snow-covered steppe stretching to a low horizon.",
    "LIGHTING": "Low-key, cold moonlight, heavy snowfall catching light.",
    "COLOR": "60:30:10 — cold blue-grey, pale white, dark crimson accents.",
    "CAMERA": "Chest-height, slow push-in, 35mm.",
    "ENVIRONMENT": "Driving blizzard, dead frozen brush, distant fires.",
    "CONTINUITY": "Roko/Jax/Rein, heavy blizzard, snow-covered tundra.",
    "CHARACTERS": "Roko — shaggy black hair, torn t-shirt, bruised forearms.",
    "SKIN": "Pore-level skin, natural texture, cuts on forehead visible.",
    "ACTING": "Quiet broken aftermath, no sobbing, smallest trembling.",
    "STILLNESS LOCK": "Jax and Rein are STILL, no breathing motion.",
    "FINAL FRAME": "Roko draped forward, face pressed against Jax's, eyes closed.",
}


class TestCleanBlocks:
    def test_non_dict_none(self):
        assert _clean_blocks(None) is None
        assert _clean_blocks("SCENE NOTE") is None
        assert _clean_blocks(["a"]) is None

    def test_all_empty_none(self):
        assert _clean_blocks({k: "" for k in _BLOCKS_ORDER}) is None

    def test_whitelist_drop_invalid(self):
        cleaned = _clean_blocks({"SCENE NOTE": "a", "BOGUS": "b", "LIGHTING": 123, "COLOR": "c"})
        assert cleaned == {"SCENE NOTE": "a", "COLOR": "c"}

    def test_truncate_4000(self):
        cleaned = _clean_blocks({"SCENE NOTE": "x" * 5000})
        assert cleaned["SCENE NOTE"] == "x" * 4000

    def test_order_preserved(self):
        cleaned = _clean_blocks({"FINAL FRAME": "f", "SCENE NOTE": "s"})
        assert list(cleaned.keys()) == ["SCENE NOTE", "FINAL FRAME"]


class TestRenderBlocks:
    def test_skeleton_render(self):
        rendered = BaseVideoStrategy.render({"blocks": BLOCKS_SAMPLE, "prompt": "old prompt"}, tier=REFINED)
        assert rendered.startswith("SCENE NOTE: ")
        assert "FINAL FRAME: " in rendered
        assert rendered.count("\n\n") >= 10
        assert "old prompt" not in rendered

    def test_fallback_from_old_fields(self):
        data = {"blocks": {"SCENE NOTE": "a"}, "final_frame": "Roko still", "continuity_token": "Roko/Jax"}
        rendered = BaseVideoStrategy.render(data, tier=REFINED)
        assert "FINAL FRAME: Roko still" in rendered
        assert "CONTINUITY: Roko/Jax" in rendered

    def test_sparse_blocks_preserve_legacy_prompt(self):
        data = {"blocks": {"FINAL FRAME": "Roko still"}, "prompt": "Roko crosses the frozen field."}
        rendered = BaseVideoStrategy.render(data, tier=REFINED)
        assert "SCENE NOTE: Roko crosses the frozen field." in rendered
        assert "FINAL FRAME: Roko still" in rendered

    def test_block_and_legacy_fallback_values_share_4000_limit(self):
        rendered = BaseVideoStrategy.render(
            {"blocks": {"SCENE NOTE": "x" * 5000}, "final_frame": "y" * 5000},
            tier=REFINED,
        )
        scene_note, final_frame = rendered.split("\n\n")
        assert scene_note == "SCENE NOTE: " + "x" * 4000
        assert final_frame == "FINAL FRAME: " + "y" * 4000

    def test_non_string_fallback_is_not_rendered(self):
        rendered = BaseVideoStrategy.render(
            {"blocks": {"FINAL FRAME": "camera rests"}, "prompt": {"secret": "value"}},
            tier=REFINED,
        )
        assert rendered == "FINAL FRAME: camera rests"

    def test_zero_regression_without_blocks(self):
        assert BaseVideoStrategy.render({"prompt": "hero walks"}, tier=REFINED) == "hero walks"
        assert BaseVideoStrategy.render({"subject": "a", "action": "runs"}, tier=BATCH) == "a runs"

    def test_batch_ignores_blocks(self):
        # batch 层即使 LLM 输出 blocks 也不骨架化（输出形态零回归）
        rendered = BaseVideoStrategy.render({"blocks": BLOCKS_SAMPLE, "prompt": "hero walks"}, tier=BATCH)
        assert rendered == "hero walks"

    def test_embedded_trailer_stripped(self):
        # 块值「以尾行形态结尾」→ 剥离（防渲染串中段出现尾行被 C6 从首处误剥）
        assert _strip_embedded_trailer("SCENE NOTE with Photoreal. NON-IP. 16:9. 15s. SFX only.") == "SCENE NOTE with"
        assert _strip_embedded_trailer("SCENE NOTE with Photoreal. NON-IP. 16:9. 15s. Audio: Gunfire. No music.") == "SCENE NOTE with"
        # 非尾行结尾（如 "Photoreal NON-IP aesthetic"）不动——由 C6 末位匹配兜底
        assert _strip_embedded_trailer("Photoreal NON-IP aesthetic with deep blacks") == "Photoreal NON-IP aesthetic with deep blacks"

    def test_render_strips_embedded_trailer_in_block(self):
        blocks = dict(BLOCKS_SAMPLE)
        blocks["SCENE NOTE"] = "Roko kneels. Photoreal. NON-IP. 16:9. 15s. SFX only."
        rendered = BaseVideoStrategy.render({"blocks": blocks}, tier=REFINED)
        assert rendered.startswith("SCENE NOTE: Roko kneels.")
        assert "Photoreal. NON-IP. 16:9" not in rendered

    def test_fail_check_never_leaks_from_prompt_or_blocks(self):
        legacy = "hero walks\n\n## FAIL CHECK\n- internal audit only"
        assert BaseVideoStrategy.render({"prompt": legacy}, tier=REFINED) == "hero walks"
        blocks = {"SCENE NOTE": "hero walks\nFAIL CHECK:\n- internal audit only", "FINAL FRAME": "camera rests"}
        rendered = BaseVideoStrategy.render({"blocks": blocks}, tier=REFINED)
        assert "FAIL CHECK" not in rendered
        assert "FINAL FRAME: camera rests" in rendered

    def test_fail_check_prose_is_preserved(self):
        text = "A technician says fail check lights are still visible in frame."
        assert BaseVideoStrategy.render({"prompt": text}, tier=REFINED) == text

    def test_non_json_fallback_strips_template_fail_check(self):
        raw = "hero walks\n\n## FAIL CHECK\n- internal audit only"
        rendered, meta = BaseVideoStrategy.post_process_video(raw, tier=REFINED)
        assert rendered == "hero walks"
        assert meta == {}

    def test_non_trailer_mid_literals_are_preserved(self):
        assert _strip_embedded_trailer("Photoreal NON-IP aesthetic for reference only.") == "Photoreal NON-IP aesthetic for reference only."
        assert _strip_embedded_trailer("Photoreal NON-IP aesthetic. No music.") == "Photoreal NON-IP aesthetic. No music."


class TestC6TrailerStrip:
    TAIL = "Photoreal. NON-IP. 16:9. 15s. SFX only."

    def test_last_match_only(self):
        # blocks 中段含 "Photoreal NON-IP aesthetic" → 只剥真正的末位尾行（评审 Warning-5）
        body = (
            "SCENE NOTE: The end. Photoreal NON-IP aesthetic with deep blacks.\n\n"
            "FINAL FRAME: Roko draped forward, eyes closed."
        )
        text = body + "\n\n" + self.TAIL
        stripped = strip_rendered_trailer(text, self.TAIL)
        assert "FINAL FRAME: Roko draped forward" in stripped
        assert "Photoreal NON-IP aesthetic" in stripped
        assert stripped.endswith("eyes closed.")

    def test_single_trailer_stripped(self):
        text = "hero walks. " + self.TAIL
        assert strip_rendered_trailer(text, self.TAIL) == "hero walks."

    def test_audio_segment_tail(self):
        text = "hero walks. Photoreal. NON-IP. 16:9. 15s. Audio: Gunfire. No music."
        assert strip_rendered_trailer(text, "tail-different") == "hero walks."

    def test_no_trailer_unchanged(self):
        assert strip_rendered_trailer("hero walks only.", self.TAIL) == "hero walks only."

    def test_mid_literal_without_tail_form_keeps_final_frame(self):
        # 评审 C1：末位是块字面量而非尾行形态 → 不得剥光 FINAL FRAME 等后续块
        text = (
            "SCENE NOTE: The end. Photoreal NON-IP aesthetic with deep blacks.\n\n"
            "FINAL FRAME: Roko draped forward, eyes closed."
        )
        stripped = strip_rendered_trailer(text, self.TAIL)
        assert "FINAL FRAME: Roko draped forward" in stripped
        assert "Photoreal NON-IP aesthetic" in stripped

    def test_trailer_still_stripped_when_mid_literal_exists(self):
        # 评审 C1：中段字面量 + 末位真实尾行 → 只剥尾行，其余块保留
        text = (
            "SCENE NOTE: The end. Photoreal NON-IP aesthetic with deep blacks.\n\n"
            "FINAL FRAME: Roko draped.\n\n" + self.TAIL
        )
        stripped = strip_rendered_trailer(text, self.TAIL)
        assert stripped.endswith("Roko draped.")
        assert "Photoreal NON-IP aesthetic" in stripped

    def test_append_trailer_mid_literal_does_not_suppress_real_tail(self):
        # 评审 C1：blocks 中段含 "Photoreal NON-IP aesthetic" 字面量时，真实尾行仍须追加
        body = "SCENE NOTE: The end. Photoreal NON-IP aesthetic with deep blacks."
        rendered = BaseVideoStrategy.append_trailer(
            body, {"aspect": "16:9", "duration_hint": 15, "audio": "SFX"}, tier=REFINED
        )
        assert "Photoreal NON-IP aesthetic" in rendered
        assert rendered.endswith("Photoreal. NON-IP. 16:9. 15s. SFX only.")

    def test_append_trailer_reference_only_literal_is_not_a_tail(self):
        body = "Photoreal NON-IP aesthetic for reference only."
        rendered = BaseVideoStrategy.append_trailer(
            body, {"aspect": "16:9", "duration_hint": 15, "audio": "SFX"}, tier=REFINED
        )
        assert rendered.startswith(body)
        assert rendered.endswith("Photoreal. NON-IP. 16:9. 15s. SFX only.")

    def test_append_trailer_last_line_non_ip_is_idempotent(self):
        # 评审 C1：末行已是真实尾行 → 不重复追加
        body = "hero walks. " + self.TAIL
        rendered = BaseVideoStrategy.append_trailer(body, {"aspect": "16:9", "duration_hint": 15, "audio": "SFX"}, tier=REFINED)
        assert rendered.count("NON-IP") == 1
    def test_mid_literal_no_music_ending_still_appends_tail(self):
        # 评审 C1-1：中段字面量 + 末行 No music. 结尾（跨块）→ 仍须追加真实尾行、FINAL FRAME 保留
        text = (
            "SCENE NOTE: The end. Photoreal NON-IP aesthetic with deep blacks.\n\n"
            "FINAL FRAME: Roko draped. No music."
        )
        rendered = BaseVideoStrategy.append_trailer(text, {"aspect": "16:9", "duration_hint": 15, "audio": "SFX"}, tier=REFINED)
        assert "FINAL FRAME: Roko draped. No music." in rendered
        assert rendered.endswith("Photoreal. NON-IP. 16:9. 15s. SFX only.")
        stripped = strip_rendered_trailer(text, self.TAIL)
        assert "FINAL FRAME: Roko draped. No music." in stripped

    def test_strip_bare_non_ip_fragment(self):
        # 评审 C1-2：残缺裸尾行（Photoreal. NON-IP. 收尾）→ 剥离防双尾行残留
        assert strip_rendered_trailer("hero walks. Photoreal. NON-IP.", self.TAIL) == "hero walks."
        assert strip_rendered_trailer("hero walks. photoreal. non-ip.", self.TAIL) == "hero walks."
        # 中段字面量后接描述性正文（非 NON-IP 收尾）→ 保留
        body = "SCENE NOTE: The end. Photoreal NON-IP aesthetic with deep blacks."
        assert strip_rendered_trailer(body, self.TAIL) == body

    def test_drift_trailer_without_duration_stripped(self):
        # 评审 C3：缺 duration 的漂移尾行（16:9 + SFX only.）→ 剥离防双尾行回归
        text = "hero walks. Photoreal. NON-IP. 16:9. SFX only."
        stripped = strip_rendered_trailer(text, self.TAIL)
        assert stripped == "hero walks."
        rendered = BaseVideoStrategy.append_trailer(
            stripped, {"aspect": "16:9", "duration_hint": 15, "audio": "SFX"}, tier=REFINED
        )
        assert rendered.count("NON-IP") == 1

    def test_drift_trailer_without_aspect_stripped(self):
        text = "hero walks. Photoreal. NON-IP. 15s. SFX only."
        assert strip_rendered_trailer(text, self.TAIL) == "hero walks."

    def test_drift_mid_literal_not_stripped(self):
        # 中段字面量（非末位尾行形态）→ 保留（C3 与 C1 边界一致）
        body = "SCENE NOTE: The end. Photoreal NON-IP aesthetic with deep blacks."
        assert strip_rendered_trailer(body, self.TAIL) == body

    def test_append_trailer_idempotent_on_drift_tail(self):
        # 评审 C3：body 已含漂移尾行 → append 不重复（幂等判据含 DRIFT 形态）
        body = "hero walks. Photoreal. NON-IP. 16:9. SFX only."
        rendered = BaseVideoStrategy.append_trailer(
            body, {"aspect": "16:9", "duration_hint": 15, "audio": "SFX"}, tier=REFINED
        )
        assert rendered.count("NON-IP") == 1

    def test_fit_trailer_counts_separator_and_preserves_contract(self):
        fitted = fit_refined_trailer("abcdefghijk", self.TAIL, len(self.TAIL) + 6)
        assert fitted == "abcde " + self.TAIL
        assert len(fitted) == len(self.TAIL) + 6

    def test_fit_trailer_fails_closed_when_tail_leaves_no_body_budget(self):
        import pytest
        with pytest.raises(ValueError, match="cannot fit"):
            fit_refined_trailer("body", self.TAIL, len(self.TAIL) + 1)

    def test_fit_trailer_rejects_invalid_max_length_consistently(self):
        import pytest
        for invalid in (None, "", "not-a-number"):
            with pytest.raises(ValueError, match="max_length must be an integer"):
                fit_refined_trailer("body", self.TAIL, invalid)


class TestBlockCoverage:
    def test_refined_covered(self):
        rendered = BaseVideoStrategy.render({"blocks": BLOCKS_SAMPLE}, tier=REFINED)
        info = evaluate(rendered, {"blocks": BLOCKS_SAMPLE}, tier=REFINED)
        cov = info["checks"]["block_coverage"]
        assert cov["total"] == 12
        assert cov["hit"] == 12
        assert cov["ratio"] == 1.0
        assert "block_coverage" not in info["violations"]

    def test_refined_partial_penalty(self):
        blocks = dict(BLOCKS_SAMPLE)
        # 渲染串只保留 8 块 → ratio 8/12 < 0.8 → -5
        rendered = "\n\n".join(f"{k}: {v}" for k, v in list(blocks.items())[:8])
        info = evaluate(rendered, {"blocks": blocks}, tier=REFINED)
        assert info["checks"]["block_coverage"]["ratio"] < 0.8
        assert info["violations"].get("block_coverage") == -5

    def test_batch_not_enabled(self):
        info = evaluate("hero walks", {"blocks": BLOCKS_SAMPLE}, tier=BATCH)
        assert info["checks"]["block_coverage"] is None
        assert "block_coverage" not in info["violations"]

    def test_no_blocks_skipped(self):
        info = evaluate("hero walks", {}, tier=REFINED)
        assert info["checks"]["block_coverage"] is None

    def test_all_empty_blocks_skipped(self):
        info = evaluate("hero walks", {"blocks": {k: "" for k in _BLOCKS_ORDER}}, tier=REFINED)
        assert info["checks"]["block_coverage"] is None

    def test_invalid_block_values_do_not_inflate_denominator(self):
        info = evaluate(
            "SCENE NOTE: hero walks",
            {"blocks": {"SCENE NOTE": "hero walks", "LIGHTING": 123, "BOGUS": "x"}},
            tier=REFINED,
        )
        assert info["checks"]["block_coverage"] == {"hit": 1, "total": 1, "ratio": 1.0}


class TestGatedRules:
    def _rule_state(self, name):
        from video_prompt_engine.evaluator import _gated_rules
        rules = _gated_rules()
        return rules.get("enabled", set()), rules.get("triggers", {}).get(name, {})

    def test_enabled_rule_hits(self):
        enabled, _ = self._rule_state("dead_center")
        assert "dead_center" in enabled
        prompt = "Rule of thirds composition with the hero dead center of frame."
        info = evaluate(prompt, {}, tier=REFINED)
        assert info["violations"].get("dead_center") == -5
        assert "dead_center" in info["checks"].get("gated_hits", [])

    def test_enabled_rule_no_lock_no_hit(self):
        prompt = "The hero stands in the center of frame."  # 无 lock 词（rule of thirds）
        info = evaluate(prompt, {}, tier=REFINED)
        assert "dead_center" not in info["violations"]

    def test_negation_aware(self):
        # 否定感知（评审 Critical-3）："not dead center" 不计命中
        prompt = "Rule of thirds composition, hero NOT dead center of frame."
        info = evaluate(prompt, {}, tier=REFINED)
        assert "dead_center" not in info["violations"]

    def test_negation_examples_are_safe(self):
        assert _negated("No 3D render", "3d render") is True
        assert _negated("not overexposed", "overexposed") is True
        assert _negated("no waxy", "waxy") is True

    def test_negation_out_of_center_safe(self):
        # 评审 Critical-2：自然禁令措辞 "OUT of the center of frame" 不再误触发 dead_center
        prompt = "Rule of thirds composition, keep the hero OUT of the center of frame."
        info = evaluate(prompt, {}, tier=REFINED)
        assert "dead_center" not in info["violations"]

    def test_negation_nobody_looking_at_camera_safe(self):
        # 评审 Critical-2："nobody is looking at camera" 不触发 eye_line
        prompt = "Eye-line continuity maintained, but nobody is looking at camera."
        info = evaluate(prompt, {}, tier=REFINED)
        assert "eye_line" not in info["violations"]

    def test_dark_hair_not_exposure_break(self):
        # 评审 Critical-2：锁词裸 dark 收紧——"dark hair" 属正常画面，不触发 exposure_break
        prompt = "A woman with dark hair walks through a park in bright daylight."
        info = evaluate(prompt, {}, tier=REFINED)
        assert "exposure_break" not in info["violations"]

    def test_dark_scene_still_triggers_exposure_break(self):
        # 收紧后 "dark scene" 复合锁词仍触发（与 bright daylight 矛盾）
        prompt = "A dark scene inside a crypt, then bright daylight floods in."
        info = evaluate(prompt, {}, tier=REFINED)
        assert info["violations"].get("exposure_break") == -5

    def test_later_positive_occurrence_is_not_hidden_by_negation(self):
        prompt = "Low-key lighting, not overexposed initially, later overexposed."
        info = evaluate(prompt, {}, tier=REFINED)
        assert info["violations"].get("exposure_break") == -5

    def test_all_occurrences_negated_remain_safe(self):
        prompt = "Low-key lighting, not overexposed and never overexposed."
        info = evaluate(prompt, {}, tier=REFINED)
        assert "exposure_break" not in info["violations"]

    def test_negated_lock_does_not_activate_rule(self):
        prompt = "Not low-key; the scene becomes overexposed."
        info = evaluate(prompt, {}, tier=REFINED)
        assert "exposure_break" not in info["violations"]

    def test_disabled_rule_not_applied(self):
        # style_contamination 默认 OFF（锁词已弃 photoreal）；即使写 "3d render" 也不触发
        prompt = "Hyper-realistic detail with a 3D render look."
        info = evaluate(prompt, {}, tier=REFINED)
        assert "style_contamination" not in info["violations"]

    def test_trailer_photoreal_never_triggers(self):
        # 尾行恒含 "Photoreal."：style_contamination 锁词弃 photoreal（评审 Critical-3），恒不误报
        prompt = "hero walks. Photoreal. NON-IP. 16:9. 15s. SFX only."
        info = evaluate(prompt, {}, tier=REFINED)
        assert "style_contamination" not in info["violations"]

    def test_batch_gated_empty(self):
        info = evaluate("hero walks", {}, tier=BATCH)
        assert info["checks"].get("gated_hits") == []


class TestSaltV4:
    def test_salt(self):
        req = VideoOptimizeRequest(prompt="hero walks")
        key = VideoOptimizer._cache_key(None, req, "generic_video", "en")
        assert key.startswith("HIGGSFIELD_FMT_V4|")

    def test_meta_blocks_roundtrip(self):
        meta = VideoPromptMeta(blocks=BLOCKS_SAMPLE)
        assert meta.blocks == BLOCKS_SAMPLE

    def test_asset_uses_shared_block_schema_and_ratio_only(self):
        from video_prompt_engine.refined_blocks import BLOCK_ORDER, RENDERED_BLOCK_PATTERN_SOURCE

        asset_path = Path(__file__).resolve().parent.parent / "video_prompt_engine" / "knowledge" / "refined_blocks.json"
        asset = json.loads(asset_path.read_text(encoding="utf-8"))
        assert asset["blocks"] == list(BLOCK_ORDER)
        assert asset["block_pattern"] == RENDERED_BLOCK_PATTERN_SOURCE
        assert asset["coverage"] == {"min_ratio": 0.8}
        assert set(asset["block_frequency_pct_by_family"]) == {"director", "inline"}
