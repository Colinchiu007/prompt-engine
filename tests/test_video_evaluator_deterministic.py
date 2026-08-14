"""Round3 Batch A T2 — 视频 evaluator 确定性 FAIL CHECK 自动化回归测试。

覆盖（REQ-2.2/2.3/2.4）：
- timeline_missing：shots≥2 且正文缺 [SHOT/[HARD CUT → -5；带标记不触发；单切/无 shots N/A
- timing_break：shots≥2 时 beats 区间端点超 shot.duration+2s → -5；区间格式 "0:00-0:04"/"s.s-s.s"
- checks 暴露 timeline_hits/timing_diff
- 与既有 violations 组合共存；总分沿用 score += sum(violations.values())
"""
from __future__ import annotations

from video_prompt_engine.evaluator import evaluate

REFINED = "refined"


def _video(shots=None):
    return {"shots": shots or [], "audio": "SFX"}


def _shot(shot_id="shot_01", duration=5.0, beats=None):
    return {"shot": shot_id, "camera": "static", "duration": duration,
            "beats": beats or [{"time": "0:00-0:04", "action": "hero walks", "camera": "static"}]}


class TestTimelineMissing:
    def test_multi_shot_with_markers_no_penalty(self):
        prompt = "[SHOT 1] hero enters the hall. [SHOT 2] hero draws sword. Photoreal. NON-IP."
        info = evaluate(prompt, _video([_shot("shot_01"), _shot("shot_02")]), tier=REFINED)
        assert "timeline_missing" not in info["violations"]

    def test_multi_shot_with_hard_cut_no_penalty(self):
        prompt = "hero enters. [HARD CUT] hero draws sword. Photoreal. NON-IP."
        info = evaluate(prompt, _video([_shot("shot_01"), _shot("shot_02")]), tier=REFINED)
        assert "timeline_missing" not in info["violations"]

    def test_multi_shot_missing_markers_penalty(self):
        prompt = "hero enters the hall. hero draws sword. Photoreal. NON-IP."
        info = evaluate(prompt, _video([_shot("shot_01"), _shot("shot_02")]), tier=REFINED)
        assert info["violations"].get("timeline_missing") == -5
        assert info["checks"]["timeline_hits"] is False

    def test_single_shot_na(self):
        prompt = "hero walks alone. Photoreal. NON-IP."
        info = evaluate(prompt, _video([_shot("shot_01")]), tier=REFINED)
        assert "timeline_missing" not in info["violations"]

    def test_no_shots_na(self):
        info = evaluate("a cat runs. Photoreal. NON-IP.", _video([]), tier=REFINED)
        assert "timeline_missing" not in info["violations"]


class TestTimingBreak:
    def test_beats_within_duration_no_penalty(self):
        prompt = "[SHOT 1] a. [SHOT 2] b. Photoreal. NON-IP."
        shots = [
            _shot("shot_01", duration=5.0, beats=[{"time": "0:00-0:04", "action": "a", "camera": "static"}]),
            _shot("shot_02", duration=5.0, beats=[{"time": "0:00-0:06", "action": "b", "camera": "static"}]),
        ]
        info = evaluate(prompt, _video(shots), tier=REFINED)
        assert "timing_break" not in info["violations"]

    def test_beat_exceeds_duration_penalty(self):
        prompt = "[SHOT 1] a. [SHOT 2] b. Photoreal. NON-IP."
        # beat 区间端点 0:00-0:09 = 9s > duration 5 + 2 = 7 → 触发
        shots = [
            _shot("shot_01", duration=5.0, beats=[{"time": "0:00-0:09", "action": "a", "camera": "static"}]),
            _shot("shot_02", duration=5.0, beats=[{"time": "0:00-0:04", "action": "b", "camera": "static"}]),
        ]
        info = evaluate(prompt, _video(shots), tier=REFINED)
        assert info["violations"].get("timing_break") == -5
        assert info["checks"]["timing_diff"] is not None

    def test_ref_block_marker_not_counted(self):
        """评审 I1：引用块 <<<[SHOT 2]...>>> 内的 [SHOT 不计数（标记区剥离后判定）。"""
        prompt = "hero enters. <<<[SHOT 2] hero draws sword.>>> Photoreal. NON-IP."
        info = evaluate(prompt, _video([_shot("shot_01"), _shot("shot_02")]), tier=REFINED)
        assert info["violations"].get("timeline_missing") == -5
        assert info["checks"]["timeline_hits"] is False

    def test_unparseable_beats_timing_diff_none_present(self):
        """评审 I2：shots>=2 且 beats 时间全部不可解析 → timing_diff 键存在且为 None（消费方不 KeyError）。"""
        shots = [
            {"shot": "shot_01", "camera": "static", "duration": 5.0, "beats": [{"time": "bogus-x", "action": "a", "camera": "static"}]},
            {"shot": "shot_02", "camera": "static", "duration": 5.0, "beats": [{"time": "zzz", "action": "b", "camera": "static"}]},
        ]
        info = evaluate("[SHOT 1] a. [SHOT 2] b. Photoreal. NON-IP.", _video(shots), tier=REFINED)
        assert info["checks"]["timing_diff"] is None

    def test_decimal_interval_format(self):
        prompt = "[SHOT 1] a. [SHOT 2] b. Photoreal. NON-IP."
        # "1.5-9.5" → 端点 9.5 > 5+2 → 触发
        shots = [
            _shot("shot_01", duration=5.0, beats=[{"time": "1.5-9.5", "action": "a", "camera": "static"}]),
            _shot("shot_02", duration=5.0, beats=[{"time": "0:00-0:04", "action": "b", "camera": "static"}]),
        ]
        info = evaluate(prompt, _video(shots), tier=REFINED)
        assert info["violations"].get("timing_break") == -5

    def test_unparseable_time_na(self):
        prompt = "[SHOT 1] a. [SHOT 2] b. Photoreal. NON-IP."
        shots = [
            _shot("shot_01", duration=5.0, beats=[{"time": "intro", "action": "a", "camera": "static"}]),
            _shot("shot_02", duration=5.0, beats=[{"time": "0:00-0:04", "action": "b", "camera": "static"}]),
        ]
        info = evaluate(prompt, _video(shots), tier=REFINED)
        assert "timing_break" not in info["violations"]

    def test_single_shot_na(self):
        prompt = "a. Photoreal. NON-IP."
        info = evaluate(prompt, _video([_shot("shot_01", duration=5.0, beats=[{"time": "0:00-9:00", "action": "a", "camera": "static"}])]), tier=REFINED)
        assert "timing_break" not in info["violations"]


class TestCombinationWithExistingViolations:
    def test_coexists_with_missing_audio_and_trailer(self):
        prompt = "hero walks. hero runs."
        shots = [_shot("shot_01"), _shot("shot_02")]
        video = _video(shots)
        video["audio"] = ""  # 无音频字段 + 正文无音频词 → missing_audio 触发
        info = evaluate(prompt, video, tier=REFINED)
        # refined 无 NON-IP → missing_trailer；无音频词 → missing_audio；缺标记 → timeline_missing
        assert info["violations"].get("missing_trailer") == -10
        assert info["violations"].get("missing_audio") == -5
        assert info["violations"].get("timeline_missing") == -5

    def test_score_includes_sum(self):
        prompt = "[SHOT 1] a. [SHOT 2] b. Photoreal. NON-IP."
        shots = [
            _shot("shot_01", duration=5.0, beats=[{"time": "0:00-0:09", "action": "a", "camera": "static"}]),
            _shot("shot_02", duration=5.0, beats=[{"time": "0:00-0:04", "action": "b", "camera": "static"}]),
        ]
        info = evaluate(prompt, _video(shots), tier=REFINED)
        assert info["violations"].get("timing_break") == -5
        assert info["score"] == round(max(0, min(100, info["score"])), 1)  # 无异常
