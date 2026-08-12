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

    def test_generic_video_fact_fidelity(self):
        sp = get_strategy("generic_video").build_system_prompt()
        assert "Fact-Fidelity" in sp
        assert "Do NOT change the subject's identity" in sp

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
        assert get_strategy("veo") is None  # 未注册 → optimizer 回退 generic_video


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
        """独立断言：视频引擎源码不得引用图片 prompt_engine。"""
        root = Path(__file__).parent.parent / "video_prompt_engine"
        offenders = []
        for f in root.rglob("*.py"):
            text = f.read_text(encoding="utf-8")
            import re
            if re.search(r"^\s*(import|from) prompt_engine", text, re.MULTILINE):
                offenders.append(str(f))
        assert offenders == [], f"视频引擎不得 import 图片引擎: {offenders}"
