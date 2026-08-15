"""Round3 Batch A T3 — 音频分层输出（audio_layers）回归测试。

覆盖（REQ-3.1/3.2/3.3/3.4/3.5）：
- _clean_audio_layers：键白名单/类型/长度清洗，非法 → None
- build_tail：audio_layers 非空 → Audio 段替换 {audio} only.；空层省略；music_off=false 省略 No music
- 零回归：无 audio_layers → 旧尾行形态不变
- missing_audio 判定表：environment/sfx/dialogue 任一非空层满足
- 链路端到端：extract_video_meta → post_process_video 渲染含 Audio 段
"""
from __future__ import annotations

from video_prompt_engine.strategies.base import BaseVideoStrategy, _clean_audio_layers
from video_prompt_engine.evaluator import evaluate
from video_prompt_engine.models import VIDEO_OUTPUT_KEYS

REFINED = "refined"


class TestCleanAudioLayers:
    def test_non_dict_none(self):
        assert _clean_audio_layers(None) is None
        assert _clean_audio_layers("sfx") is None
        assert _clean_audio_layers(["sfx"]) is None

    def test_all_empty_none(self):
        assert _clean_audio_layers({"environment": "", "sfx": "  ", "dialogue": None}) is None

    def test_whitelist_and_truncate(self):
        cleaned = _clean_audio_layers({
            "environment": "x" * 300, "sfx": "gunfire", "music_off": True, "bogus": "drop",
        })
        assert cleaned["environment"] == "x" * 200
        assert cleaned["sfx"] == "gunfire"
        assert cleaned["music_off"] is True
        assert "bogus" not in cleaned

    def test_music_off_string_coercion(self):
        assert _clean_audio_layers({"sfx": "a", "music_off": "true"})["music_off"] is True
        assert _clean_audio_layers({"sfx": "a", "music_off": "false"})["music_off"] is False
        assert "music_off" not in _clean_audio_layers({"sfx": "a", "music_off": "maybe"})

    def test_output_keys_include_audio_layers(self):
        assert "audio_layers" in VIDEO_OUTPUT_KEYS


class TestBuildTailAudioSegment:
    def test_full_layers(self):
        meta = {"aspect": "16:9", "duration_hint": 15, "audio_layers": {
            "environment": "forest ambience", "sfx": "gunfire", "dialogue": "\"Run!\"", "music_off": True}}
        tail = BaseVideoStrategy.build_tail(meta)
        assert tail == 'Photoreal. NON-IP. 16:9. 15s. Audio: Environmental forest ambience. SFX: gunfire. Dialogue: "Run!". No music.'

    def test_empty_layers_omitted(self):
        meta = {"aspect": "16:9", "duration_hint": 15, "audio_layers": {"sfx": "gunfire"}}
        tail = BaseVideoStrategy.build_tail(meta)
        assert tail == "Photoreal. NON-IP. 16:9. 15s. Audio: SFX: gunfire."

    def test_music_off_false_omits_no_music(self):
        meta = {"aspect": "16:9", "duration_hint": 15, "audio_layers": {"dialogue": "\"hi\"", "music_off": False}}
        tail = BaseVideoStrategy.build_tail(meta)
        assert tail == 'Photoreal. NON-IP. 16:9. 15s. Audio: Dialogue: "hi".'
        assert "No music" not in tail

    def test_zero_regression_legacy_tail(self):
        meta = {"aspect": "16:9", "duration_hint": 15, "audio": "SFX"}
        assert BaseVideoStrategy.build_tail(meta) == "Photoreal. NON-IP. 16:9. 15s. SFX only."
        assert BaseVideoStrategy.build_tail({"aspect": "16:9"}) == "Photoreal. NON-IP. 16:9. 15s. SFX only."


class TestMissingAudioJudgment:
    def _evaluate(self, layers):
        video = {"shots": [], "audio": ""}
        if layers is not None:
            video["audio_layers"] = layers
        return evaluate("a cat runs. Photoreal. NON-IP.", video, tier=REFINED)

    def test_sfx_layer_satisfies(self):
        assert "missing_audio" not in self._evaluate({"sfx": "gunfire"})["violations"]

    def test_dialogue_layer_satisfies(self):
        assert "missing_audio" not in self._evaluate({"dialogue": "\"Run!\""})["violations"]

    def test_environment_layer_satisfies(self):
        assert "missing_audio" not in self._evaluate({"environment": "forest"})["violations"]

    def test_no_layers_legacy_behavior(self):
        # 无 audio_layers + audio 空 + 正文无音频词 → 仍触发（零回归）
        assert self._evaluate(None)["violations"].get("missing_audio") == -5


class TestEndToEndRender:
    def test_post_process_renders_audio_segment(self):
        raw = ('{"prompt": "hero walks in the woods.", "aspect": "16:9", "duration_hint": 8, '
               '"audio": "SFX", "audio_layers": {"environment": "wind rustling", "sfx": "footsteps", "music_off": true}, '
               '"excluded_characters": [], "no_swap_pairs": [], "color_ratio": "60:30:10", "shots": []}')
        rendered, meta = BaseVideoStrategy.post_process_video(raw, creative_level=7, tier=REFINED)
        assert rendered == ("hero walks in the woods. Photoreal. NON-IP. 16:9. 8s. "
                            "Audio: Environmental wind rustling. SFX: footsteps. No music.")
        assert meta["audio_layers"] == {"environment": "wind rustling", "sfx": "footsteps", "music_off": True}


class TestReviewFixes:
    """评审修复回归：W1（batch 判定表越权）/ I9（int music_off）/ I10（空层残缺尾行）/ C1（Audio 尾行截断）。"""

    def test_batch_with_audio_layers_still_needs_text_audio(self):
        """评审 W1：batch 无尾行，audio_layers 不接管正文音频词检查（正文含否定词仍扣分）。"""
        video = {"shots": [], "audio": "", "audio_layers": {"sfx": "gunfire"}}
        info = evaluate("a cat runs. no sound.", video, tier="batch")
        assert info["violations"].get("missing_audio") == -5

    def test_music_off_int_normalized(self):
        """评审 I9：int 0/1 归一为布尔。"""
        from video_prompt_engine.strategies.base import _clean_audio_layers
        assert _clean_audio_layers({"sfx": "x", "music_off": 1})["music_off"] is True
        assert _clean_audio_layers({"sfx": "x", "music_off": 0})["music_off"] is False

    def test_build_tail_empty_layers_falls_back(self):
        """评审 I10：直调 build_tail 传空 audio_layers dict 不产出残缺 `Audio: ` 尾行。"""
        tail = BaseVideoStrategy.build_tail(
            {"aspect": "16:9", "duration_hint": 15, "audio": "SFX", "audio_layers": {}}
        )
        assert tail == "Photoreal. NON-IP. 16:9. 15s. SFX only."

    def test_audio_tail_survives_budget_truncation(self):
        """评审 C1：refined + audio_layers，LLM 直出带偏差尾行且超 max_length 时，
        C6 尾行剥离正则必须识别 Audio 段形态，截断后重 append 规范尾行，不产出双尾行。"""
        from video_prompt_engine.optimizer import VideoOptimizer
        from video_prompt_engine.models import VideoOptimizeRequest

        class FakeProvider:
            model_name = "mock-video"

            def call(self, *a, **k):
                body = "hero walks through a dark forest with heavy footsteps and distant thunder. " * 15
                llm_trailer = " Photoreal. NON-IP. 16:9. 8s. Audio: Environmental wind rustling. SFX: boom boom. No music."
                raw = ('{"prompt": "%s", "aspect": "16:9", "audio": "SFX", "duration_hint": 8, '
                       '"audio_layers": {"environment": "wind", "sfx": "boom", "music_off": true}, '
                       '"excluded_characters": [], "no_swap_pairs": [], "color_ratio": "60:30:10", "shots": []}'
                       % (body + llm_trailer))
                return raw, 100

        o = VideoOptimizer()
        o._provider = FakeProvider()
        req = VideoOptimizeRequest(prompt="forest chase", platform="generic_video", max_length=200, creative_level=8)
        result = o.optimize(req)
        assert result.video is not None
        assert result.optimized_prompt.count("Photoreal") == 1, "双尾行：Audio 段尾行未被 C6 剥离"
        assert result.optimized_prompt.endswith(
            "Photoreal. NON-IP. 16:9. 8s. Audio: Environmental wind. SFX: boom. No music."
        )
