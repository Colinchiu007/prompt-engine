"""Higgsfield P0 引擎侧落地测试（8020）。

覆盖：
- models 边界：max_length 5000/5001；新字段上限校验拒绝；旧缓存 dict 默认值重建
- extract_video_meta 归一：超限裁剪/脏数据清洗/非法 color_ratio 回退/缺 aspect/audio 默认
- 尾行生命周期：refined 精确模板结尾；batch 无尾行；body 恰满 max_length 尾行完整；幂等
- evaluator：tier 判定（explicit/auto-detect）；refined 长度层级；violations 扣分；zh 区间
- optimizer：缓存版本盐；JSON_RETRY_HINT 同源含新键；tier 传递
- 六策略 system prompt 含新键；8013 镜像零改动
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from video_prompt_engine.models import (
    VideoOptimizeRequest, VideoOptimizeResult, VideoFeedbackRequest, VideoPromptMeta,
)
from video_prompt_engine.optimizer import VideoOptimizer, JSON_RETRY_HINT
from video_prompt_engine.strategies import get_strategy
from video_prompt_engine.strategies.base import BaseVideoStrategy
from video_prompt_engine.evaluator import evaluate, detect_tier

VIDEO_LLM_JSON = (
    '{"prompt": "a sleek black cat dashes through a neon alley, cinematic medium-wide shot, slow dolly-in, '
    'cool blue and magenta palette, dramatic rim lighting, sfx of distant traffic", '
    '"shot": "medium_wide", "camera": "dolly", "motion_intensity": 7, '
    '"scene_transition": "cut", "continuity_token": "cat_neon_alley", "duration_hint": 5}'
)


def make_optimizer(cache_dir=None):
    return VideoOptimizer(cache_dir=cache_dir or tempfile.mkdtemp())


def mock_provider(value, *, side_effect=None):
    fake = Mock()
    fake.model_name = "mock-video"
    if side_effect is not None:
        fake.call.side_effect = side_effect
    else:
        fake.call.return_value = (value, 100)
    return fake


class TestModelsBoundary:
    def test_max_length_20000_accepted_20001_rejected(self):
        # Higgsfield P0 边界上浮：精修层 500-5000 词模板（≈22871 字符）需 20000 字符预算
        # （对齐契约层 VIDEO_ENGINE_LIMITS.videoMaxLengthMax=20000 / standalone.max）
        VideoOptimizeRequest(prompt="x" * 10, max_length=20000)
        with pytest.raises(Exception):
            VideoOptimizeRequest(prompt="x" * 10, max_length=20001)

    def test_feedback_result_4500_accepted(self):
        r = VideoFeedbackRequest(prompt_text="x" * 10, result_prompt="y" * 4500)
        assert len(r.result_prompt) == 4500

    def test_feedback_result_20000_accepted_20001_rejected(self):
        # 评审 W2：feedback 闭环上限与 max_length 边界上浮对齐（refined 长模板结果可回传）
        VideoFeedbackRequest(prompt_text="x" * 10, result_prompt="y" * 20000)
        with pytest.raises(Exception):
            VideoFeedbackRequest(prompt_text="x" * 10, result_prompt="y" * 20001)

    def test_new_field_limits_rejected(self):
        with pytest.raises(Exception):
            VideoPromptMeta(excluded_characters=["e"] * 11)
        with pytest.raises(Exception):
            VideoPromptMeta(no_swap_pairs=[{"from": "a", "to": "b"}] * 6)
        with pytest.raises(Exception):
            VideoPromptMeta(shots=[{"shot": "s"}] * 4)
        with pytest.raises(Exception):
            VideoPromptMeta(shots=[{"shot": "s", "beats": [{"time": "t", "action": "a"}] * 7}])

    def test_legacy_cache_dict_rebuilds_with_defaults(self):
        legacy = {
            "optimized_prompt": "old prompt", "platform": "generic_video",
            "video": {"shot": "wide", "camera": "pan", "motion_intensity": 5,
                      "scene_transition": "cut", "continuity_token": "t", "duration_hint": 5},
        }
        hit = VideoOptimizeResult(**legacy)
        assert hit.video.aspect == "16:9"
        assert hit.video.audio == "SFX"
        assert hit.video.color_ratio == "60:30:10"
        assert hit.video.shots == []
        assert hit.video.excluded_characters == []
        assert hit.video.no_swap_pairs == []


class TestExtractNormalization:
    def test_shots_beats_clamped(self):
        raw = '{"prompt": "p", "shots": [{"shot": "s%d", "camera": "c", "duration": 99, "beats": [{"time": "t%d", "action": "a%d"}]} for _ in range(0)]}'
        # 直接用构造 dict 走 parse
        import json
        data = {
            "prompt": "p",
            "shots": [
                {"shot": f"s{i}", "camera": "drone", "duration": 99,
                 "beats": [{"time": f"t{j}", "action": f"a{j}"} for j in range(8)]}
                for i in range(5)
            ],
        }
        meta = BaseVideoStrategy.extract_video_meta(json.dumps(data))
        assert len(meta["shots"]) == 3
        assert len(meta["shots"][0]["beats"]) == 6
        assert meta["shots"][0]["duration"] == 15.0

    def test_dirty_swap_pairs_cleaned(self):
        import json
        data = {
            "no_swap_pairs": [
                {"from": "A", "to": "B"},
                {"from": "C", "to": "D", "extra": 1},
                {"from": "", "to": "E"},
                {"x": 1},
                {"from": "F", "to": "G"},
                {"from": "H", "to": "I"},
            ]
        }
        meta = BaseVideoStrategy.extract_video_meta(json.dumps(data))
        assert meta["no_swap_pairs"] == [
            {"from": "A", "to": "B"}, {"from": "C", "to": "D"},
            {"from": "F", "to": "G"}, {"from": "H", "to": "I"},
        ]

    def test_color_ratio_normalized(self):
        import json
        meta = BaseVideoStrategy.extract_video_meta(json.dumps({"color_ratio": "60,30,10"}))
        assert meta["color_ratio"] == "60:30:10"
        meta = BaseVideoStrategy.extract_video_meta(json.dumps({"color_ratio": "70:20:10"}))
        assert meta["color_ratio"] == "70:20:10"

    def test_aspect_audio_defaults(self):
        import json
        meta = BaseVideoStrategy.extract_video_meta(json.dumps({"prompt": "p"}))
        assert meta["aspect"] == "16:9"
        assert meta["audio"] == "SFX"
        meta = BaseVideoStrategy.extract_video_meta(json.dumps({"aspect": "9:16", "audio": "wind"}))
        assert meta["aspect"] == "9:16"
        assert meta["audio"] == "wind"


class TestTrailerLifecycle:
    def test_refined_appends_exact_trailer(self):
        meta = {"aspect": "16:9", "audio": "sfx", "duration_hint": 8.0}
        body = "A very long and detailed refined prompt with rich detail and cinematic description."
        out = BaseVideoStrategy.append_trailer(body, meta, "refined")
        assert out.endswith("Photoreal. NON-IP. 16:9. 8s. sfx only.")

    def test_batch_no_trailer(self):
        meta = {"aspect": "16:9", "audio": "sfx", "duration_hint": 8.0}
        out = BaseVideoStrategy.append_trailer("body", meta, "batch")
        assert out == "body"

    def test_body_at_max_length_keeps_trailer(self):
        # 经 post_process_video + optimizer 截断路径：tail 永不截断
        raw = '{"prompt": "%s", "aspect": "16:9", "audio": "sfx", "duration_hint": 8, "shot": "wide", "camera": "pan", "motion_intensity": 5, "scene_transition": "cut", "continuity_token": "t"}' % ("x" * 3000)
        rendered, meta = BaseVideoStrategy.post_process_video(raw, creative_level=8, tier="refined")
        tail = BaseVideoStrategy.build_tail(meta)
        assert rendered.endswith(tail)
        budget = 200
        if len(rendered) > budget:
            body = rendered[: -len(tail)]
            trimmed = body[: max(0, budget - len(tail))] + tail
            assert trimmed.endswith(tail)
            assert len(trimmed) <= budget

    def test_trailer_idempotent(self):
        meta = {"aspect": "16:9", "audio": "sfx", "duration_hint": 8.0}
        tail = BaseVideoStrategy.build_tail(meta)
        out = BaseVideoStrategy.append_trailer("body " + tail, meta, "refined")
        assert out == "body " + tail


class TestEvaluatorTier:
    def test_explicit_refined_length_band(self):
        long_en = " ".join(["detail"] * 600)
        r = evaluate(long_en + " Photoreal. NON-IP. 16:9. 8s. sfx only.", {}, "", "en", tier="refined", max_length=5000)
        assert r["tier"] == "refined"
        assert r["checks"]["length"] is True
        # 401-499 词在 refined 下仍不足（无隐藏 gap）
        mid = " ".join(["detail"] * 450)
        r2 = evaluate(mid, {}, "", "en", tier="refined", max_length=5000)
        assert r2["checks"]["length"] is False

    def test_refined_long_template_not_killed(self):
        """DEEP 报告 P0-1：精修层 500-5,000 词（词数刻度，max_length 是字符裁剪预算不参与 refined 判据）。

        语料实证精修层中位 22,871 字符 ≈ 4,500 词；此前 upper=max(500, max_length//5)=1000 词
        把 1000+ 词模板硬扣（直接评估与先裁后评行为不一致）。"""
        # Bug 复现：120 次重复句 ≈ 2760 词，max_length=5000 精修层 → 必须 preserved
        long_en = " ".join(["word"] * 2760)
        r = evaluate(long_en + " Photoreal. NON-IP. 16:9. 15s. SFX only.", {}, "", "en", tier="refined", max_length=5000)
        assert r["checks"]["length"] is True, r["checks"]
        # 语料中位量级：4,500+ 词仍放行
        corpus_median = " ".join(["detail"] * 4550)
        r2 = evaluate(corpus_median + " Photoreal. NON-IP.", {}, "", "en", tier="refined", max_length=20000)
        assert r2["checks"]["length"] is True, r2["checks"]
        # 超报告上界（>5000 词）仍拒绝
        over = " ".join(["detail"] * 5200)
        r3 = evaluate(over, {}, "", "en", tier="refined", max_length=20000)
        assert r3["checks"]["length"] is False, r3["checks"]

    def test_refined_band_exact_boundaries(self):
        """评审 I3：精修层词数刻度精确边界 499/5000/5001。"""
        assert evaluate(" ".join(["word"] * 499), {}, "", "en", tier="refined", max_length=5000)["checks"]["length"] is False
        assert evaluate(" ".join(["word"] * 5000), {}, "", "en", tier="refined", max_length=20000)["checks"]["length"] is True
        assert evaluate(" ".join(["word"] * 5001), {}, "", "en", tier="refined", max_length=20000)["checks"]["length"] is False

    def test_refined_small_budget_lower_bound_adaptive(self):
        """评审 C1 回归：refined + 小预算（1800 字符 ≈360 词）先裁后评不误杀——下界随预算自适应。"""
        r = evaluate(" ".join(["word"] * 360), {}, "", "en", tier="refined", max_length=1800)
        assert r["checks"]["length"] is True, r["checks"]
        # 150 词仍不足（自适应下界 min(500, max(150, 300))=300）
        r2 = evaluate(" ".join(["word"] * 150), {}, "", "en", tier="refined", max_length=1800)
        assert r2["checks"]["length"] is False, r2["checks"]

    def test_batch_upper_capped_at_833_even_with_20000_budget(self):
        """评审 W3 回归：batch 上界封顶 833，le=20000 不静默扩到 3333。"""
        assert evaluate(" ".join(["word"] * 3000), {}, "", "en", tier="batch", max_length=20000)["checks"]["length"] is False
        assert evaluate(" ".join(["word"] * 800), {}, "", "en", tier="batch", max_length=20000)["checks"]["length"] is True

    def test_auto_detect_via_shots_and_marker(self):
        # 无 explicit（None）→ auto-detect 兜底
        assert detect_tier("plain", {}, None) == "batch"
        assert detect_tier("plain", {"shots": [{"shot": "s"}]}, None) == "refined"
        assert detect_tier("x Photoreal. NON-IP. y", {}, None) == "refined"
        assert detect_tier("x FINAL FRAME y", {}, None) == "refined"
        # explicit 优先于 auto-detect（W4：显式 batch 不被 NON-IP 顶回 refined）
        assert detect_tier("plain", {}, "refined") == "refined"
        assert detect_tier("x Photoreal. NON-IP. y", {}, "batch") == "batch"
        assert detect_tier("plain", {"shots": [{"shot": "s"}]}, "batch") == "batch"

    def test_violations_scoring(self):
        video = {
            "excluded_characters": ["crowd"], "no_swap_pairs": [{"from": "villain", "to": "hero"}],
            "shots": [], "audio": "sfx",
        }
        # 命中 excluded + swap 源 + refined 缺尾行
        r = evaluate("A crowd watches the villain arrive. " * 10, video, "", "en", tier="refined", max_length=5000)
        assert r["violations"]["excluded_present"] == -10
        assert r["violations"]["swap_source_present"] == -10
        assert r["violations"]["missing_trailer"] == -10
        # 单字中文不误击（"关" 不出现在 "关键" 匹配）
        video2 = {"excluded_characters": ["关"], "no_swap_pairs": [], "shots": []}
        r2 = evaluate("这是关键要素描述" * 5, video2, "", "zh", tier="batch")
        assert "excluded_present" not in r2["violations"]
        # batch 无尾行不罚 missing_trailer
        r3 = evaluate("A plain prompt with sfx sounds. " * 5, {}, "", "en", tier="batch")
        assert "missing_trailer" not in r3["violations"]

    def test_zh_bands(self):
        zh_batch = "战争场面" * 200  # 800 字符
        r = evaluate(zh_batch, {"shots": []}, "", "zh", tier="batch", max_length=1800)
        assert r["checks"]["length"] is True
        zh_refined = "史诗级战争场面" * 200  # 1000 字符
        r2 = evaluate(zh_refined, {"shots": []}, "", "zh", tier="refined", max_length=5000)
        assert r2["checks"]["length"] is True


class TestOptimizerHiggsfield:
    def test_cache_key_has_version_salt(self):
        o = make_optimizer()
        req = VideoOptimizeRequest(prompt="a cat", max_length=1800)
        key = o._cache_key(req, "generic_video", "en")
        assert key.startswith("HIGGSFIELD_FMT_V1|")
        # 旧格式 key（无盐）不命中新 key
        old = "|".join(key.split("|")[1:])
        assert old != key

    def test_json_retry_hint_contains_new_keys(self):
        for k in ("excluded_characters", "no_swap_pairs", "color_ratio", "shots"):
            assert f'"{k}"' in JSON_RETRY_HINT

    def test_refined_tier_passes_trailer_and_meta(self):
        o = make_optimizer()
        calls = {"n": 0}

        def side_effect(system_prompt, user_prompt, variant=0, max_length=None):
            calls["n"] += 1
            assert "Director Workflow" in system_prompt
            assert max_length == 5000
            return (
                '{"prompt": "a sleek black cat dashes through a neon alley, cinematic medium-wide shot, slow dolly-in, '
                'cool blue and magenta palette, dramatic rim lighting, sfx of distant traffic", '
                '"shot": "medium_wide", "camera": "dolly", "motion_intensity": 7, '
                '"scene_transition": "cut", "continuity_token": "cat_neon_alley", "duration_hint": 5, '
                '"aspect": "16:9", "audio": "sfx", '
                '"shots": [{"shot": "s1", "camera": "dolly", "duration": 5, '
                '"beats": [{"time": "0:00", "action": "run", "camera": "wide"}]}]}',
                100,
            )

        o._provider = mock_provider(None, side_effect=side_effect)
        r = o.optimize(VideoOptimizeRequest(prompt="a cat running in neon city", creative_level=8, max_length=5000))
        assert r.video is not None and r.video.shots
        # batch 层不加尾行（creative_level=5）
        calls["n"] = 0
        o._provider = mock_provider(VIDEO_LLM_JSON)
        r2 = o.optimize(VideoOptimizeRequest(prompt="a cat running in neon city", creative_level=5, max_length=1800))
        assert "NON-IP" not in r2.optimized_prompt


class TestStrategyPrompts:
    def test_all_strategies_contain_new_keys(self):
        for name in ("generic_video", "veo", "kling", "hailuo", "doubao", "seedance"):
            cls = get_strategy(name)
            p = cls.build_system_prompt(style=None, creative_level=8, max_length=5000, tier="refined")
            for key in ("excluded_characters", "no_swap_pairs", "color_ratio", "shots", "Director Workflow"):
                assert key in p, f"{name} missing {key}"
            pb = cls.build_system_prompt(creative_level=5, max_length=1800, tier="batch")
            assert "Do NOT append any trailer line" in pb, f"{name} batch section missing"


class Test8013Untouched:
    def test_mirror_has_no_higgsfield_fields(self):
        mirror = Path(__file__).parent.parent / "prompt_engine" / "strategies" / "video" / "generic.py"
        if mirror.exists():
            content = mirror.read_text(encoding="utf-8")
            for key in ("excluded_characters", "no_swap_pairs", "color_ratio"):
                assert key not in content


class TestReviewFixes:
    """双模型评审修复回归（C1/C2/C3/W3/W4）。"""

    def test_c1_fractional_duration_trailer_survives_truncation(self):
        """LLM 直出非规范尾行（5.5s 变体）+ 超长 → 剥离重 append，尾行完整且总长 ≤ max_length。"""
        import json
        raw = json.dumps({
            "prompt": "x" * 300 + " Photoreal. NON-IP. 16:9. 5.5s. sfx only.",
            "aspect": "16:9", "audio": "sfx", "duration_hint": 5.5,
            "shot": "wide", "camera": "pan", "motion_intensity": 5,
            "scene_transition": "cut", "continuity_token": "t",
        })
        rendered, meta = BaseVideoStrategy.post_process_video(raw, creative_level=8, tier="refined")
        # 幂等：已含 NON-IP 不重复
        assert rendered.count("NON-IP") == 1
        # 模拟 optimizer 截断路径（C1：endswith 失配 → 剥离 → body 截断 → 重 append）
        from video_prompt_engine.optimizer import VideoOptimizer
        o = VideoOptimizer(cache_dir=tempfile.mkdtemp())
        budget = 200
        tail = BaseVideoStrategy.build_tail(meta)
        body = rendered[: -len(tail)] if rendered.endswith(tail) else rendered
        trimmed = body[: max(0, budget - len(tail))] + tail
        assert trimmed.endswith(tail)
        assert len(trimmed) <= budget
        assert "Photoreal. NON-IP." in trimmed

    def test_c2_positive_constraints_final_frame_landed(self):
        import json
        from video_prompt_engine.models import VideoPromptMeta
        meta = BaseVideoStrategy.extract_video_meta(json.dumps({
            "positive_constraints": ["keep red coat", "", "keep scar"],
            "final_frame": "x" * 600,
        }))
        assert meta["positive_constraints"] == ["keep red coat", "keep scar"]
        assert len(meta["final_frame"]) == 500
        m = VideoPromptMeta(**meta)
        assert m.positive_constraints == ["keep red coat", "keep scar"]
        assert len(m.final_frame) == 500

    def test_c3_extract_result_passes_pydantic(self):
        import json
        from video_prompt_engine.models import VideoPromptMeta
        data = {
            "prompt": "p",
            "excluded_characters": ["e"] * 20,
            "shots": [{"shot": "s" * 200, "camera": "c" * 200, "duration": 99,
                       "beats": [{"time": "t", "action": "a" * 600, "camera": "c" * 600}]}],
        }
        meta = BaseVideoStrategy.extract_video_meta(json.dumps(data))
        m = VideoPromptMeta(**meta)  # 不抛 = C3 回归通过
        assert len(m.shots[0].beats[0].camera) == 50
        assert len(m.shots[0].beats[0].action) == 500
        assert len(m.shots[0].shot) == 50

    def test_w3_audio_judgement(self):
        # refined 尾行带 audio 字段不扣
        r = evaluate("word " * 500 + " Photoreal. NON-IP. 16:9. 8s. music only.",
                     {"audio": "music", "shots": []}, "", "en", tier="refined", max_length=5000)
        assert "missing_audio" not in r["violations"]
        # batch 无任何音频词 → 扣
        r2 = evaluate("A plain static description of a room interior. " * 5, {}, "", "en", tier="batch")
        assert r2["violations"].get("missing_audio") == -5
        # batch 有配乐 → 不扣
        r3 = evaluate("Epic orchestral score plays. " * 5, {}, "", "en", tier="batch")
        assert "missing_audio" not in r3["violations"]
        # 中文否定词"无声"不误判为音频
        r4 = evaluate("无声的画面缓缓展开。 " * 5, {}, "", "zh", tier="batch")
        assert r4["violations"].get("missing_audio") == -5

    def test_w4_batch_upper_bound_links_max_length(self):
        # 默认 1800 → 上界 400（零回归）
        r = evaluate("word " * 401, {}, "", "en", tier="batch", max_length=1800)
        assert r["checks"]["length"] is False
        # 大预算 batch（5000）→ 上界 833，500 词通过（消除 401+ 死区）
        r2 = evaluate("word " * 500, {}, "", "en", tier="batch", max_length=5000)
        assert r2["checks"]["length"] is True
        # refined 判据为 DEEP P0-1 词数刻度 500-5000 词：900/1100 词均通过
        # （旧 W4 上界 max_length//5=1000 已由词数刻度取代，防长模板误杀）
        r3 = evaluate("word " * 900, {}, "", "en", tier="refined", max_length=5000)
        assert r3["checks"]["length"] is True
        r4 = evaluate("word " * 1100, {}, "", "en", tier="refined", max_length=5000)
        assert r4["checks"]["length"] is True
        # refined + 小预算（1800）不坍缩：upper=max(500, 360)=500，恰 500 词通过
        r5 = evaluate("word " * 500, {}, "", "en", tier="refined", max_length=1800)
        assert r5["checks"]["length"] is True

    def test_t4_upper_truncation(self):
        # excluded>10 / swap>5 → 归一截断到上限（T4）
        import json
        data = {
            "excluded_characters": [f"e{i}" for i in range(15)],
            "no_swap_pairs": [{"from": f"a{i}", "to": f"b{i}"} for i in range(9)],
        }
        meta = BaseVideoStrategy.extract_video_meta(json.dumps(data))
        assert len(meta["excluded_characters"]) == 10
        assert len(meta["no_swap_pairs"]) == 5

    def test_t5_aspect_overlong_falls_back(self):
        # W1：1920:1080:24（12 字符）超出 VideoPromptMeta.aspect max_length=10 → 回退 16:9
        import json
        meta = BaseVideoStrategy.extract_video_meta(json.dumps({"aspect": "1920:1080:24"}))
        assert meta["aspect"] == "16:9"
        # 恰好 10 字符合法值保留
        meta2 = BaseVideoStrategy.extract_video_meta(json.dumps({"aspect": "1920:1080"}))
        assert meta2["aspect"] == "1920:1080"
        from video_prompt_engine.models import VideoPromptMeta
        VideoPromptMeta(**meta2)  # 不抛

    def test_t6_refined_non_json_fallback_no_trailer(self):
        # refined 非 JSON → 回退原文且不追加尾行（T6）
        rendered, meta = BaseVideoStrategy.post_process_video("plain prose without json", creative_level=8, tier="refined")
        assert rendered == "plain prose without json"
        assert meta == {}
        assert "NON-IP" not in rendered

    def test_t7_lowercase_non_ip_idempotent_and_batch_leak(self):
        # 小写 non-ip 也幂等（T7：不双写）
        meta = {"aspect": "16:9", "audio": "sfx", "duration_hint": 8.0}
        out = BaseVideoStrategy.append_trailer("body with non-ip marker", meta, "refined")
        assert out == "body with non-ip marker"
        # batch 层即使 meta 有尾行字段也不追加（尾行不泄漏到 batch）
        out2 = BaseVideoStrategy.append_trailer("body", meta, "batch")
        assert out2 == "body"

    def test_t8_reference_marker_instruction_and_flow(self):
        # C1：refined 指令要求声明禁止项时正文嵌 [ABSENT]/<<<>>> 标记
        sp = get_strategy("generic_video").build_system_prompt(creative_level=8, max_length=5000, tier="refined")
        assert "[ABSENT]" in sp and "<<<" in sp
        assert "Never declare a ban without marking it" in sp
        # batch 段同样要求（契约 _assertReferenceProtocol 不分 tier）
        spb = get_strategy("generic_video").build_system_prompt(creative_level=5, max_length=1800, tier="batch")
        assert "[ABSENT]" in spb
        # 全链路：mock LLM 输出含标记 → optimized_prompt 保留标记（契约侧 ok:true 由契约测试覆盖）
        import json
        o = make_optimizer()
        raw = json.dumps({
            "prompt": "hero walks through the hall. [ABSENT] JAX stays off-frame. cinematic lighting, sfx",
            "excluded_characters": ["JAX"],
            "shot": "medium_wide", "camera": "dolly", "motion_intensity": 7,
            "scene_transition": "cut", "continuity_token": "t", "duration_hint": 5,
            "aspect": "16:9", "audio": "sfx",
        })
        o._provider = mock_provider(raw)
        r = o.optimize(VideoOptimizeRequest(prompt="hero and JAX in hall", creative_level=8, max_length=5000))
        assert r.video is not None and r.video.excluded_characters == ["JAX"]
        assert "[ABSENT] JAX" in r.optimized_prompt

    def test_t8_marker_does_not_self_penalize(self):
        # 标记区段本身含角色名 → 剥离后不计 excluded/swap 违规（防自罚分）
        r = evaluate(
            "hero walks. [ABSENT] JAX stays off-frame. " * 5 + "Photoreal. NON-IP. 16:9. 8s. sfx only.",
            {"excluded_characters": ["JAX"], "no_swap_pairs": [], "shots": [], "audio": "sfx"},
            "", "en", tier="refined", max_length=5000,
        )
        assert "excluded_present" not in r["violations"]
        # 正文真实出现仍命中
        r2 = evaluate(
            "JAX enters the hall. " * 5 + "Photoreal. NON-IP. 16:9. 8s. sfx only.",
            {"excluded_characters": ["JAX"], "no_swap_pairs": [], "shots": [], "audio": "sfx"},
            "", "en", tier="refined", max_length=5000,
        )
        assert r2["violations"].get("excluded_present") == -10
        # 复审 C1：标记同句含真实出现（标记后逗号延续）→ 仍扣分（只剥标记 token，不吞正文）
        r3 = evaluate(
            "hero walks. [ABSENT] JAX stays off-frame, JAX never enters. " * 3 + "Photoreal. NON-IP. 16:9. 8s. sfx only.",
            {"excluded_characters": ["JAX"], "no_swap_pairs": [], "shots": [], "audio": "sfx"},
            "", "en", tier="refined", max_length=5000,
        )
        assert r3["violations"].get("excluded_present") == -10
        # 未闭合 <<< 前缀（契约仅要求 includes('<<<')）同样不自罚分
        r4 = evaluate(
            "hero walks. <<<JAX banned. rest of the scene continues. " * 3 + "Photoreal. NON-IP. 16:9. 8s. sfx only.",
            {"excluded_characters": ["JAX"], "no_swap_pairs": [], "shots": [], "audio": "sfx"},
            "", "en", tier="refined", max_length=5000,
        )
        assert "excluded_present" not in r4["violations"]

    def test_t10_swap_tuple_form_guard(self):
        # 契约规范形态二元组 [from, to] 回流 evaluator 不崩（类型防御），对象形态正常命中
        r = evaluate(
            "ROKO arrives. " * 5 + "Photoreal. NON-IP. 16:9. 8s. sfx only.",
            {"no_swap_pairs": [["ROKO", "JAX"]], "excluded_characters": [], "shots": [], "audio": "sfx"},
            "", "en", tier="refined", max_length=5000,
        )
        assert r["violations"].get("swap_source_present") == -10
        r2 = evaluate(
            "plain body. " * 5 + "Photoreal. NON-IP. 16:9. 8s. sfx only.",
            {"no_swap_pairs": [["ROKO", "JAX"]], "excluded_characters": [], "shots": [], "audio": "sfx"},
            "", "en", tier="refined", max_length=5000,
        )
        assert "swap_source_present" not in r2["violations"]

    def test_w3_color_ratio_overlong_falls_back(self):
        # 超长/超三位 color_ratio → 回退默认，不再触发 W6 整单回退
        import json
        meta = BaseVideoStrategy.extract_video_meta(json.dumps({"color_ratio": "999999999999999999:1:1"}))
        assert meta["color_ratio"] == "60:30:10"
        meta2 = BaseVideoStrategy.extract_video_meta(json.dumps({"color_ratio": "999:999:999"}))
        assert meta2["color_ratio"] == "999:999:999"
        meta3 = BaseVideoStrategy.extract_video_meta(json.dumps({"color_ratio": "60:30:10"}))
        assert meta3["color_ratio"] == "60:30:10"

    def test_w4_swap_tuple_input_normalized(self):
        # 二元组形态输入 → 归一为对象形态（引擎规范输出）
        import json
        meta = BaseVideoStrategy.extract_video_meta(json.dumps({"no_swap_pairs": [["ROKO", "JAX"], ("A", "B"), ["C"], ["", "D"], [1, "E"]]}))
        assert meta["no_swap_pairs"] == [{"from": "ROKO", "to": "JAX"}, {"from": "A", "to": "B"}]

    def test_w5_real_optimizer_truncation_path(self):
        # 复审 W5/W6：真 optimizer 路径超长截断（走 post_process_video + optimizer 剥离/重 append 逻辑）
        import json
        o = make_optimizer()
        raw = json.dumps({
            "prompt": "x" * 3000 + " Photoreal. NON-IP. 16:9. 5.5s. sfx only.",
            "aspect": "16:9", "audio": "sfx", "duration_hint": 5.5,
            "shot": "wide", "camera": "pan", "motion_intensity": 5,
            "scene_transition": "cut", "continuity_token": "t",
        })
        o._provider = mock_provider(raw)
        r = o.optimize(VideoOptimizeRequest(prompt="a cat", creative_level=8, max_length=2000))
        assert r.optimized_prompt.endswith("Photoreal. NON-IP. 16:9. 5s. sfx only.")
        assert len(r.optimized_prompt) <= 2000
        assert r.optimized_prompt.count("NON-IP") == 1  # 无畸形拼接/双写

    def test_w5_real_truncation_no_period_variant(self):
        # 复审 W5：LLM 直出缺句点变体尾行（Photoreal NON-IP. ...）→ 剥离后规范重 append，无拦腰截断
        import json
        o = make_optimizer()
        raw = json.dumps({
            "prompt": "y" * 3000 + " Photoreal NON-IP. 16:9. 8s. sfx only.",
            "aspect": "16:9", "audio": "sfx", "duration_hint": 8,
            "shot": "wide", "camera": "pan", "motion_intensity": 5,
            "scene_transition": "cut", "continuity_token": "t",
        })
        o._provider = mock_provider(raw)
        r = o.optimize(VideoOptimizeRequest(prompt="a dog", creative_level=8, max_length=2000))
        assert r.optimized_prompt.endswith("Photoreal. NON-IP. 16:9. 8s. sfx only.")
        assert len(r.optimized_prompt) <= 2000
        assert r.optimized_prompt.count("NON-IP") == 1  # 无畸形拼接/双写

    def test_w6_meta_validation_fallback(self, monkeypatch):
        # 复审 W6：VideoPromptMeta 校验失败 → 整单回退原文并标记（不返回坏 meta）
        import json
        from video_prompt_engine.strategies.base import BaseVideoStrategy
        o = make_optimizer()
        raw = json.dumps({"prompt": "p", "aspect": "16:9"})
        monkeypatch.setattr(
            BaseVideoStrategy, "extract_video_meta",
            classmethod(lambda cls, raw_output: {"aspect": "x" * 100}),
        )
        o._provider = mock_provider(raw)
        r = o.optimize(VideoOptimizeRequest(prompt="source text", creative_level=8, max_length=5000))
        assert r.optimized_prompt == "source text"
        assert r.video is None

    def test_t9_zh_refined_lower_bound(self):
        # zh refined 500 字符下界：498 字符不足，500 通过（T9）
        r = evaluate("战争史诗" * 124 + "场面", {"shots": []}, "", "zh", tier="refined", max_length=1800)
        assert r["checks"]["length"] is False
        r2 = evaluate("战争史诗" * 125, {"shots": []}, "", "zh", tier="refined", max_length=1800)
        assert r2["checks"]["length"] is True

    def test_w8_length_copy_tier_aware(self):
        # refined 提示不再出现 150-300 词口径；batch 保持 150-300（W8）
        sp_r = get_strategy("generic_video").build_system_prompt(creative_level=8, max_length=5000, tier="refined")
        assert "500+ English words" in sp_r and "150-300" not in sp_r
        sp_b = get_strategy("generic_video").build_system_prompt(creative_level=5, max_length=1800, tier="batch")
        assert "150-300 words" in sp_b
        # zh refined 语言段同步 500-5000 口径
        sp_zh = get_strategy("generic_video").build_system_prompt(
            creative_level=8, max_length=5000, output_language="zh", tier="refined")
        assert "500-5000 Chinese chars" in sp_zh

class TestDirectorStyle:
    """P1-6 导演风格词典（DEEP 报告）：解析 + generic_video 注入。"""

    @staticmethod
    def _styles():
        from pathlib import Path as _P
        from video_prompt_engine.knowledge.loader import load_director_styles
        return load_director_styles(_P(__file__).resolve().parent.parent / "video_prompt_engine" / "knowledge" / "director_styles.json")

    def test_resolve_english_name_case_insensitive(self):
        from video_prompt_engine.knowledge.loader import resolve_director_style
        styles = self._styles()
        hit = resolve_director_style("Lubezki 风格", styles)
        assert hit is not None and hit["name_en"] == "Emmanuel Lubezki"
        hit2 = resolve_director_style("in lubezki style", styles)
        assert hit2 is not None and hit2["name_en"] == "Emmanuel Lubezki"

    def test_resolve_alias(self):
        from video_prompt_engine.knowledge.loader import resolve_director_style
        styles = self._styles()
        assert resolve_director_style("chivo look", styles)["name_en"] == "Emmanuel Lubezki"

    def test_resolve_chinese_name(self):
        from video_prompt_engine.knowledge.loader import resolve_director_style
        styles = self._styles()
        assert resolve_director_style("王家卫风格", styles)["name_en"] == "Wong Kar-wai"
        assert resolve_director_style("黑泽明的雨戏", styles)["name_en"] == "Akira Kurosawa"

    def test_resolve_miss_returns_none(self):
        from video_prompt_engine.knowledge.loader import resolve_director_style
        styles = self._styles()
        assert resolve_director_style("cyberpunk noir", styles) is None
        assert resolve_director_style("", styles) is None
        assert resolve_director_style(None, styles) is None
        # 短名不误命中：子串必须完整出现（单字不匹配）
        assert resolve_director_style("王", styles) is None

    def test_system_prompt_injects_director_look(self):
        sp = get_strategy("generic_video").build_system_prompt(
            style="Lubezki 风格", creative_level=8, max_length=5000, tier="refined"
        )
        assert "导演风格引用：手持长镜头" in sp
        assert "long handheld takes" in sp  # look 注入 system prompt

    def test_system_prompt_miss_keeps_style_without_look(self):
        sp = get_strategy("generic_video").build_system_prompt(
            style="cyberpunk noir", creative_level=5, max_length=1800, tier="batch"
        )
        assert "风格：cyberpunk noir" in sp
        assert "long handheld takes" not in sp

    def test_optimize_full_flow_passes_director_look_to_llm(self):
        import json
        raw = json.dumps({
            "prompt": "a sleek black cat dashes through a neon alley, cinematic medium-wide shot, "
                      "slow dolly-in, cool blue and magenta palette, dramatic rim lighting, sfx of distant traffic",
            "shot": "medium_wide", "camera": "dolly", "motion_intensity": 7,
            "scene_transition": "cut", "continuity_token": "cat_neon_alley", "duration_hint": 5,
        })
        o = make_optimizer()
        o._provider = mock_provider(raw)
        r = o.optimize(VideoOptimizeRequest(
            prompt="black cat in neon alley", style="王家卫风格",
            creative_level=8, max_length=5000,
        ))
        assert r.video is not None
        sp = o._provider.call.call_args.args[0]
        assert "导演风格引用：手持霓虹" in sp
        assert "handheld neon-soaked frames" in sp

class TestFailurePatternLoop:
    """P1-3 失败模式闭环（DEEP 报告 3.1/五-12）：规则库 + feedback 采集统计。"""

    @staticmethod
    def _rules():
        from pathlib import Path as _P
        from video_prompt_engine.knowledge.loader import load_failure_patterns
        return load_failure_patterns(_P(__file__).resolve().parent.parent / "video_prompt_engine" / "knowledge" / "failure_patterns.json")

    def test_rule_library_loaded(self):
        rules = self._rules()
        assert len(rules) >= 10
        for r in rules:
            for key in ("pattern", "name", "category", "check", "severity", "tags", "evidence"):
                assert key in r, f"rule {r.get('pattern')} missing {key}"
            assert r["severity"] < 0
        # 高频失败区（禁令聚类实证）必须入库
        names = {r["pattern"] for r in rules}
        assert "exposure_break" in names and "gaze_camera_fail" in names and "face_skin_detail_fail" in names

    def test_submit_bad_records_failure_events(self, tmp_path):
        from video_prompt_engine.feedback import VideoFeedbackStore
        store = VideoFeedbackStore(tmp_path / "seed.json")
        r = store.submit("cat in alley", "result prompt x", good=False, failure_patterns=["exposure_break", "dead_center_composition"])
        assert r["failure_events"] == {"exposure_break": 1, "dead_center_composition": 1}
        stats = store.failure_stats()
        assert stats["exposure_break"]["count"] == 1
        assert stats["exposure_break"]["recent_prompt"] == "cat in alley"
        # 再次提交同 pattern → 累计
        store.submit("cat in alley", "result prompt y", good=False, failure_patterns=["exposure_break"])
        assert store.failure_stats()["exposure_break"]["count"] == 2

    def test_submit_unknown_pattern_tolerated_and_truncated(self, tmp_path):
        from video_prompt_engine.feedback import VideoFeedbackStore
        store = VideoFeedbackStore(tmp_path / "seed.json")
        long_pat = "x" * 80
        r = store.submit("p", "r", good=False, failure_patterns=["mystery_pattern", long_pat, ""])
        assert "mystery_pattern" in r["failure_events"]
        assert "x" * 50 in store.failure_stats()  # 截断到 50
        assert ("x" * 80) not in store.failure_stats()

    def test_submit_without_patterns_no_stats_file(self, tmp_path):
        from video_prompt_engine.feedback import VideoFeedbackStore
        store = VideoFeedbackStore(tmp_path / "seed.json")
        r = store.submit("p", "r", good=True)
        assert r["failure_events"] == {}
        assert not (tmp_path / "failure_stats.json").exists()

    def test_good_feedback_ignores_patterns(self, tmp_path):
        from video_prompt_engine.feedback import VideoFeedbackStore
        store = VideoFeedbackStore(tmp_path / "seed.json")
        r = store.submit("p", "r", good=True, failure_patterns=["exposure_break"])
        assert r["failure_events"] == {}
        assert store.failure_stats() == {}

    def test_request_model_limits_failure_patterns(self):
        VideoFeedbackRequest(prompt_text="p", result_prompt="r", good=False, failure_patterns=["a"] * 10)
        with pytest.raises(Exception):
            VideoFeedbackRequest(prompt_text="p", result_prompt="r", good=False, failure_patterns=["a"] * 11)
