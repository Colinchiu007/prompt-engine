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

from video_prompt_engine.strategies.base import (
    BaseVideoStrategy, _clean_blocks, _BLOCKS_ORDER, _strip_embedded_trailer,
)
from video_prompt_engine.optimizer import VideoOptimizer, strip_rendered_trailer
from video_prompt_engine.evaluator import evaluate
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

    def test_append_trailer_last_line_non_ip_is_idempotent(self):
        # 评审 C1：末行已是真实尾行 → 不重复追加
        body = "hero walks. " + self.TAIL
        rendered = BaseVideoStrategy.append_trailer(body, {"aspect": "16:9", "duration_hint": 15, "audio": "SFX"}, tier=REFINED)
        assert rendered.count("NON-IP") == 1


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