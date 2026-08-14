"""独立视频提示词优化引擎测试。

覆盖：模型/契约、策略注册表、知识库、API（mock LLM）、独立断言（无 import prompt_engine）。
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from video_prompt_engine.models import (
    VideoOptimizeRequest, VideoPlatformType, normalize_video_platform,
    assert_no_sensitive_context, CONTEXT_KEYS,
)
from video_prompt_engine.strategies import get_strategy, list_strategies
from video_prompt_engine.knowledge.loader import load_keywords_video, load_seed_video_prompts
from video_prompt_engine.optimizer import VideoOptimizer

VIDEO_LLM_JSON = (
    '{"prompt": "a sleek black cat dashes through a neon alley, cinematic medium-wide shot, slow dolly-in, '
    'cool blue and magenta palette, dramatic rim lighting", '
    '"shot": "medium_wide", "camera": "dolly", "motion_intensity": 7, '
    '"scene_transition": "cut", "continuity_token": "cat_neon_alley", "duration_hint": 5}'
)


class TestModels:
    def test_platform_normalize_alias_and_unknown(self):
        assert normalize_video_platform("veo3") == "veo"
        assert normalize_video_platform("kling-v3") == "kling"
        assert normalize_video_platform("seedance-2.0") == "seedance"
        assert normalize_video_platform("unknown_platform") == "generic_video"

    def test_batch_limit(self):
        from video_prompt_engine.models import VideoBatchOptimizeRequest
        with pytest.raises(Exception):
            VideoBatchOptimizeRequest(requests=[VideoOptimizeRequest(prompt=f"p{i}") for i in range(21)])

    def test_sensitive_context_rejected(self):
        with pytest.raises(ValueError, match="敏感"):
            assert_no_sensitive_context({"api_key": "sk-xxx"})
        with pytest.raises(ValueError, match="敏感"):
            assert_no_sensitive_context({"nested": {"token": "t"}})

    def test_context_whitelist(self):
        assert {"synopsis", "character", "setting", "character_list", "full_text"} <= CONTEXT_KEYS


class TestStrategies:
    def test_registry(self):
        assert "generic_video" in list_strategies()
        assert "seedance" in list_strategies()
        assert {"veo", "kling", "hailuo", "doubao"} <= set(list_strategies())

    def test_generic_video_fact_fidelity(self):
        sp = get_strategy("generic_video").build_system_prompt()
        assert "Fact-Fidelity" in sp
        assert "Do NOT change the subject's identity" in sp

    def test_default_max_length_1800(self):
        """视频提示词专业长度：默认 max_length=1800（非 500），支持 200-5000。"""
        req = VideoOptimizeRequest(prompt="x")
        assert req.max_length == 1800

    def test_generic_video_detail_instruction(self):
        """策略要求详细（150-300 词），避免短提示词。"""
        sp = get_strategy("generic_video").build_system_prompt()
        assert "150-300 words" in sp
        assert "RICH, DETAILED" in sp

    def test_seedance_multimodal(self):
        sp = get_strategy("seedance").build_system_prompt()
        assert "Multimodal" in sp
        assert "@" in sp

    def test_post_process_video_structured(self):
        rendered, meta = get_strategy("generic_video").post_process_video(VIDEO_LLM_JSON)
        assert "neon alley" in rendered
        assert meta["shot"] == "medium_wide"
        assert meta["motion_intensity"] == 7
        assert meta["continuity_token"] == "cat_neon_alley"

    def test_unknown_platform_fallback(self):
        assert get_strategy("runway") is None  # 未注册 → optimizer 回退 generic_video
        assert get_strategy("veo") is not None  # 专项策略已注册


class TestKnowledge:
    def test_keywords_loaded(self):
        kw = load_keywords_video(Path(__file__).parent.parent / "video_prompt_engine/knowledge/keywords_video.json")
        assert len(kw) >= 7
        assert kw["action"] and kw["camera"]

    def test_seeds_loaded(self):
        seeds = load_seed_video_prompts(Path(__file__).parent.parent / "video_prompt_engine/knowledge/seed_video_prompts.json")
        assert len(seeds) >= 5

    def test_optimizer_keywords_hint(self):
        o = VideoOptimizer()
        hint = o.keywords_hint("a cat walking through a neon cyberpunk street")
        assert isinstance(hint, str)


class TestOptimizer:
    def _mock_provider(self, value, error=None):
        class FakeProvider:
            model_name = "mock-video"
            def call(self, *a, **k):
                if error:
                    raise error
                return value, 100
        return FakeProvider()

    def test_optimize_structured(self):
        o = VideoOptimizer()
        o._provider = self._mock_provider(VIDEO_LLM_JSON)
        req = VideoOptimizeRequest(prompt="a cat running", platform="generic_video")
        result = o.optimize(req)
        assert result.optimized_prompt
        assert "neon alley" in result.optimized_prompt
        assert result.video is not None
        assert result.video.shot == "medium_wide"

    def test_optimize_empty_falls_back(self):
        o = VideoOptimizer()
        o._provider = self._mock_provider("")
        req = VideoOptimizeRequest(prompt="原文兜底", platform="generic_video")
        result = o.optimize(req)
        assert result.optimized_prompt == "原文兜底"

    def test_optimize_missing_key_fail_closed(self):
        o = VideoOptimizer()
        o._provider = self._mock_provider(None, error=RuntimeError("LLM API Key 未配置"))
        req = VideoOptimizeRequest(prompt="x", platform="generic_video")
        result = o.optimize(req)
        assert result.error and "API Key" in result.error
        assert result.optimized_prompt == ""

    def test_batch_order_and_nonempty(self):
        o = VideoOptimizer()
        o._provider = self._mock_provider(VIDEO_LLM_JSON)
        reqs = [VideoOptimizeRequest(prompt=f"scene {i}", platform="generic_video") for i in range(12)]
        results = o.optimize_batch(reqs)
        assert len(results) == 12
        assert all(r.optimized_prompt for r in results)
    def test_think_block_stripped(self):
        """真实 LLM（MiniMax-M2.7）输出含 <think> 推理块时剥离后再结构化。"""
        raw_with_think = "<think>Let me plan the shot...</think>{\"prompt\": \"a cat runs\", \"shot\": \"wide\", \"camera\": \"dolly\", \"motion_intensity\": 6, \"scene_transition\": \"cut\", \"continuity_token\": \"cat\", \"duration_hint\": 5}"
        from unittest.mock import Mock
        # 独立缓存目录：避免同 prompt 命中 SQLite 缓存绕过 mock
        import tempfile
        o = VideoOptimizer(cache_dir=tempfile.mkdtemp())
        o._provider = Mock()
        o._provider.call.return_value = (raw_with_think, 100)
        o._provider.model_name = "mock-video"
        result = o.optimize(VideoOptimizeRequest(prompt="a cat running", platform="generic_video"))
        assert "<think>" not in result.optimized_prompt
        assert result.video is not None
        assert result.video.shot == "wide"



class TestApi:
    def test_health(self):
        from video_prompt_engine.api.rest import app
        client = TestClient(app)
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["engine"] == "video"

    def test_platforms(self):
        from video_prompt_engine.api.rest import app
        client = TestClient(app)
        r = client.get("/v1/video/platforms")
        assert r.status_code == 200
        assert "seedance" in r.json()["platforms"]

    def test_keywords(self):
        from video_prompt_engine.api.rest import app
        client = TestClient(app)
        r = client.get("/v1/video/keywords")
        assert r.status_code == 200
        assert "camera" in r.json()["dimensions"]

    def test_batch_12_single(self):
        from video_prompt_engine.api import rest
        from video_prompt_engine.models import VideoOptimizeResult
        fake = rest.VideoOptimizer.__new__(rest.VideoOptimizer)
        fake.optimize = lambda req: VideoOptimizeResult(optimized_prompt="ok", platform="generic_video")
        rest._optimizer = fake
        try:
            client = TestClient(rest.app)
            payload = {"requests": [{"prompt": f"scene {i}", "platform": "generic_video"} for i in range(12)]}
            r = client.post("/v1/video/optimize/batch", json=payload)
            assert r.status_code == 200
            assert len(r.json()) == 12
        finally:
            rest._optimizer = None


class TestIndependence:
    def test_no_import_prompt_engine(self):
        """独立断言：视频引擎源码不得引用图片引擎领域层 prompt_engine。

        允许依赖领域无关共享内核 prompt_engine_core（openspec engine-shared-core
        「领域层代码零耦合」条款：不得 import 对方领域层，允许依赖 prompt_engine_core）。
        负向前瞻 (?!_) 保证 prompt_engine_core 等共享内核模块不命中。
        """
        root = Path(__file__).parent.parent / "video_prompt_engine"
        offenders = []
        for f in root.rglob("*.py"):
            text = f.read_text(encoding="utf-8")
            import re
            if re.search(r"^\s*(import|from) prompt_engine(?!_)", text, re.MULTILINE):
                offenders.append(str(f))
        assert offenders == [], f"视频引擎不得 import 图片引擎: {offenders}"


# === video-prompt-lens-discipline 镜头纪律规则测试 ===

VIDEO_LLM_JSON_LENS = (
    '{"prompt": "a sleek black cat dashes through a neon alley, cinematic medium-wide shot, slow dolly-in, '
    'cool blue and magenta palette, dramatic rim lighting, FINAL FRAME: the cat sits still, camera rests, no text", '
    '"shot": "medium_wide", "camera": "dolly", "motion_intensity": 7, '
    '"scene_transition": "cut", "continuity_token": "cat_neon_alley", "duration_hint": 5, '
    '"positive_constraints": ["camera stays at ground level", "all fallen bodies are distinct"], '
    '"final_frame": "cat sits still on wet asphalt, rim light holds, camera locked off, no text"}'
)


class TestLensDiscipline:
    def test_meta_new_fields_defaults(self):
        from video_prompt_engine.models import VideoPromptMeta
        m = VideoPromptMeta()
        assert m.positive_constraints == []
        assert m.final_frame == ""

    def test_meta_new_fields_set(self):
        from video_prompt_engine.models import VideoPromptMeta
        m = VideoPromptMeta(positive_constraints=["a", "b"], final_frame="end state")
        assert m.positive_constraints == ["a", "b"]
        assert m.final_frame == "end state"

    def test_extract_video_meta_new_fields(self):
        meta = get_strategy("generic_video").extract_video_meta(VIDEO_LLM_JSON_LENS)
        assert meta["positive_constraints"] == ["camera stays at ground level", "all fallen bodies are distinct"]
        assert meta["final_frame"] == "cat sits still on wet asphalt, rim light holds, camera locked off, no text"

    def test_extract_video_meta_string_constraints(self):
        """字符串形态（换行/分号拆分）双形态兼容。"""
        raw = VIDEO_LLM_JSON_LENS.replace(
            '"positive_constraints": ["camera stays at ground level", "all fallen bodies are distinct"]',
            '"positive_constraints": "camera stays at ground level; all fallen bodies are distinct"',
        )
        meta = get_strategy("generic_video").extract_video_meta(raw)
        assert meta["positive_constraints"] == ["camera stays at ground level", "all fallen bodies are distinct"]

    def test_extract_video_meta_old_json_zero_regression(self):
        """旧 7 字段 JSON：新字段默认值，不拒绝。"""
        meta = get_strategy("generic_video").extract_video_meta(VIDEO_LLM_JSON)
        assert meta["positive_constraints"] == []
        assert meta["final_frame"] == ""
        assert meta["shot"] == "medium_wide"

    def test_extract_video_meta_constraint_cap(self):
        raw = VIDEO_LLM_JSON_LENS.replace(
            '"positive_constraints": ["camera stays at ground level", "all fallen bodies are distinct"]',
            '"positive_constraints": ["c1", "c2", "c3", "c4", "c5", "c6", "c7", "c8", "c9", "c10", "c11"]',
        )
        meta = get_strategy("generic_video").extract_video_meta(raw)
        assert len(meta["positive_constraints"]) == 10

    def test_lens_discipline_in_generic(self):
        sp = get_strategy("generic_video").build_system_prompt()
        assert "Lens Discipline (MANDATORY)" in sp
        assert "One primary camera move per shot" in sp
        assert "At most 3 recognizable characters" in sp
        assert "FINAL FRAME" in sp
        assert "Negative Prompt Discipline" in sp
        assert "plausible failure classes" in sp

    def test_lens_discipline_in_all_platforms(self):
        for platform in ("seedance", "veo", "kling", "hailuo", "doubao"):
            sp = get_strategy(platform).build_system_prompt()
            assert "Lens Discipline (MANDATORY)" in sp, platform
            assert "One primary camera move per shot" in sp, platform
            # optimizer 真实链路：character_count 透传（子类覆盖签名必须同步），不抛 TypeError 且注入 EXACT N
            sp_n = get_strategy(platform).build_system_prompt(character_count=2)
            assert "EXACT 2 CHARACTERS" in sp_n, platform

    def test_character_count_injected(self):
        sp = get_strategy("generic_video").build_system_prompt(character_count=2)
        assert "EXACT 2 CHARACTERS" in sp
        sp0 = get_strategy("generic_video").build_system_prompt(character_count=None)
        assert "EXACT 2 CHARACTERS" not in sp0
        assert "EXACT 1 CHARACTERS" not in sp0
    def test_seedance_keeps_existing_sections(self):
        sp = get_strategy("seedance").build_system_prompt()
        assert "Multimodal Input Constraints" in sp
        assert "Fact-Fidelity" in sp
        assert "Lens Discipline (MANDATORY)" in sp

    def test_output_format_mentions_new_fields(self):
        sp = get_strategy("generic_video").build_system_prompt()
        assert "positive_constraints" in sp
        assert "final_frame" in sp

    def test_derive_character_count(self):
        from video_prompt_engine.optimizer import derive_character_count
        assert derive_character_count(None) is None
        assert derive_character_count({"character_list": [{"name": "a"}, {"name": "b"}]}) == 2
        assert derive_character_count({"character": {"name": "a"}}) == 1
        assert derive_character_count({"synopsis": "x"}) is None
