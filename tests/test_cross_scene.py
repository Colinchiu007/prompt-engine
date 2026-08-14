"""Round3 Batch B — 跨镜状态包（prev_final_frame）回归测试。

覆盖（评审修订版）：
- T1 请求校验：prev_final_frame 缺省/合法/超 1000 → pydantic 拒绝；final_frame 上限 1000
- T2 缓存隔离：异 prev_final_frame → 异 key；盐 HIGGSFIELD_FMT_V4
- T3 承接指令注入：提供/缺省两形态
- T4 continuity_check：英文正反例/泛词不稀释/角色名硬判据/中文白名单/整句重合回退/缺省跳过
- 择优稳定性：continuity_break 不逆转明显更优候选
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from video_prompt_engine.models import VideoOptimizeRequest, VideoPromptMeta
from video_prompt_engine.optimizer import VideoOptimizer
from video_prompt_engine.prompt_builder import VideoPromptBuilder
from video_prompt_engine.evaluator import evaluate, select_best


class TestRequestValidation:
    def test_missing_ok(self):
        req = VideoOptimizeRequest(prompt="hero walks")
        assert req.prev_final_frame is None

    def test_valid_value(self):
        req = VideoOptimizeRequest(prompt="hero walks", prev_final_frame="Jax kneels in the snow.")
        assert req.prev_final_frame == "Jax kneels in the snow."

    def test_over_1000_rejected(self):
        with pytest.raises(ValidationError):
            VideoOptimizeRequest(prompt="hero walks", prev_final_frame="x" * 1001)

    def test_final_frame_upper_bound_1000(self):
        meta = VideoPromptMeta(final_frame="x" * 1000)
        assert len(meta.final_frame) == 1000
        with pytest.raises(ValidationError):
            VideoPromptMeta(final_frame="x" * 1001)


class TestCacheKey:
    def _key(self, prev):
        req = VideoOptimizeRequest(prompt="hero walks in snow", prev_final_frame=prev)
        return VideoOptimizer._cache_key(None, req, "generic_video", "en")

    def test_prev_final_frame_component(self):
        assert self._key("Jax kneels, eyes closed") != self._key("Jax stands at the door")

    def test_salt_v4(self):
        assert "HIGGSFIELD_FMT_V4" in self._key(None)

    def test_missing_prev_stable(self):
        assert self._key(None) == self._key(None)


class TestContinuitySection:
    def test_injected_when_provided(self):
        section = VideoPromptBuilder.build_continuity_section("Jax kneels in the snow", tier="refined")
        assert "SCENE Continuity" in section
        assert "SCENE pickup" in section
        assert "Jax kneels in the snow" in section

    def test_absent_when_missing(self):
        assert VideoPromptBuilder.build_continuity_section(None, tier="refined") == ""
        assert VideoPromptBuilder.build_continuity_section("   ", tier="batch") == ""

    def test_batch_short_form(self):
        section = VideoPromptBuilder.build_continuity_section("Jax kneels", tier="batch")
        assert "SCENE pickup" in section
        assert "NEVER contradict" in section


REFINED = "refined"


class TestContinuityCheck:
    def test_en_positive_reuse(self):
        prev = "Jax kneels on the frozen steppe, his eyes fully closed, blood on his lip."
        prompt = "SCENE pickup: Jax kneels on the frozen steppe, eyes closed, blood on his lip. Roko raises his hand."
        info = evaluate(prompt, {}, tier=REFINED, prev_final_frame=prev)
        assert info["checks"]["continuity_method"] == "wordlist"
        assert info["checks"]["continuity_ratio"] >= 0.4
        assert "continuity_break" not in info["violations"]

    def test_en_negative_rewrite(self):
        prev = "Jax kneels on the frozen steppe, his eyes fully closed, blood on his lip."
        prompt = "Roko storms through a burning city at noon, sword raised, shouting."
        info = evaluate(prompt, {}, tier=REFINED, prev_final_frame=prev)
        assert info["checks"]["continuity_ratio"] < 0.4
        assert info["violations"].get("continuity_break") == -5

    def test_en_generic_words_do_not_inflate(self):
        # 泛词（camera/frame/light/left/right）全命中也不足以通过：实体缺失 → 低命中
        prev = "Jax kneels in the snow, his eyes closed, blood on his split lip."
        prompt = "camera frame light left right screen shot background. nothing else."
        info = evaluate(prompt, {}, tier=REFINED, prev_final_frame=prev)
        assert info["checks"]["continuity_ratio"] < 0.4
        assert "continuity_break" in info["violations"]

    def test_en_character_list_hard_requirement(self):
        prev = "Jax kneels in the snow, eyes closed."
        prompt = "Jax kneels in the snow, eyes closed. Roko raises his hand."
        info = evaluate(prompt, {}, tier=REFINED, prev_final_frame=prev, character_list=["Roko", "Jax"])
        assert "continuity_break" not in info["violations"]
        # 角色 Jax 被丢 → 硬判据失败，即使其余 token 命中
        prompt2 = "Roko raises his hand and looks away."
        info2 = evaluate(prompt2, {}, tier=REFINED, prev_final_frame=prev, character_list=["Roko", "Jax"])
        assert info2["violations"].get("continuity_break") == -5
        assert "Jax" in info2["checks"].get("continuity_missing", [])

    def test_zh_whitelist_positive(self):
        prev = "贾克斯跪在雪地里，闭着眼睛，嘴唇上带着血。"
        prompt = "承接：贾克斯跪在雪地里，闭着眼。罗科缓缓举起手。"
        info = evaluate(prompt, {}, tier=REFINED, prev_final_frame=prev, character_list=["贾克斯", "罗科"])
        assert info["checks"]["continuity_method"] == "whitelist"
        assert info["checks"]["continuity_ratio"] >= 0.6
        assert "continuity_break" not in info["violations"]

    def test_zh_paraphrase_not_punished_by_bigram(self):
        # 评审 Critical-1 修复：改写（非逐字复用）不得因 2-gram 恒误报；
        # 角色名/姿势词命中即通过——这里角色名+姿势词都在
        prev = "贾克斯跪在雪地里，闭着眼睛，嘴唇上带着血。"
        prompt = "罗科看到贾克斯仍跪在雪地，闭眼，血还在唇边，于是慢慢靠近。"
        info = evaluate(prompt, {}, tier=REFINED, prev_final_frame=prev, character_list=["贾克斯"])
        assert "continuity_break" not in info["violations"]

    def test_zh_fallback_ratio_when_no_whitelist(self):
        # 终态不含姿势/位置词、无角色白名单 → 整句重合度回退（评审修订：无 2-gram 误报）
        prev = "贾克斯，罗科，血迹，黄昏，暴风雪。"
        prompt = "贾克斯，罗科，血迹，黄昏，暴风雪。罗科缓缓靠近。"
        info = evaluate(prompt, {}, tier=REFINED, prev_final_frame=prev)
        assert info["checks"]["continuity_method"] == "ratio"
        assert info["checks"]["continuity_ratio"] >= 0.5

    def test_missing_prev_skipped(self):
        info = evaluate("hero walks", {}, tier=REFINED)
        assert info["checks"]["continuity_ratio"] is None
        assert "continuity_break" not in info["violations"]


class TestSelectBestStability:
    def test_continuity_break_does_not_reverse_clear_better(self):
        # 候选 A：承接正确但缺尾行（-10）；候选 B：完全承接（-5 continuity 之外无大扣）
        prev = "Jax kneels on the frozen steppe, eyes closed, blood on lip."
        good = (
            "SCENE pickup: Jax kneels on the frozen steppe, eyes closed, blood on his lip. "
            "Roko reaches forward slowly. Photoreal. NON-IP. 16:9. 15s. SFX only.",
            {"audio": "SFX", "aspect": "16:9", "duration_hint": 15},
        )
        bad = (
            "Roko storms through a burning city at noon, sword raised, shouting. "
            "Photoreal. NON-IP. 16:9. 15s. SFX only.",
            {"audio": "SFX", "aspect": "16:9", "duration_hint": 15},
        )
        best, _, score = select_best([good, bad], tier=REFINED, prev_final_frame=prev)
        assert best == good[0]
        assert score >= 0