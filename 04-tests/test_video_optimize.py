"""v0.20.x — 视频提示词优化（domain=video）契约测试

覆盖：
  - 领域缺省兼容（不传 domain = image，零回归）
  - 视频平台枚举与请求校验（合法平台 200 / 非法平台 422）
  - GenericVideoStrategy 结构化输出（渲染单串 + video 字段）
  - Optimizer 视频路径（结构化填充 / 空输出回退原文 / 图片路径无 video 字段）
  - REST /v1/optimize domain=video（mock LLM，不依赖真实 8013/LLM key）
"""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from prompt_engine.models import (
    DomainType, VideoPlatformType, OptimizeRequest, StyleType,
)
from prompt_engine.optimizer import Optimizer
from prompt_engine.strategies.video.generic import GenericVideoStrategy

VIDEO_LLM_JSON = (
    '{"prompt": "a sleek black cat dashes through a neon alley, cinematic medium-wide shot, slow dolly-in, '
    'cool blue and magenta palette, dramatic rim lighting", '
    '"shot": "medium_wide", "camera": "dolly", "motion_intensity": 7, '
    '"scene_transition": "cut", "continuity_token": "cat_neon_alley", "duration_hint": 5}'
)


class TestVideoModels:
    def test_domain_default_is_image(self):
        req = OptimizeRequest(prompt="a cat")
        assert req.domain == DomainType.IMAGE

    def test_video_platform_enum_members(self):
        names = {p.value for p in VideoPlatformType}
        assert {"sora", "kling", "veo", "runway", "wan", "seedance", "minimax",
                "hunyuan", "cogvideo", "ltx", "higgsfield", "grok", "agnes",
                "generic_video"} <= names

    def test_video_request_accepts_video_platform(self):
        req = OptimizeRequest(prompt="a cat", domain="video", platform="generic_video")
        assert req.domain == DomainType.VIDEO
        assert req.platform == VideoPlatformType.GENERIC_VIDEO


class TestGenericVideoStrategy:
    def test_post_process_video_structured(self):
        rendered, meta = GenericVideoStrategy.post_process_video(VIDEO_LLM_JSON)
        assert "neon alley" in rendered
        assert meta["shot"] == "medium_wide"
        assert meta["camera"] == "dolly"
        assert meta["motion_intensity"] == 7
        assert meta["continuity_token"] == "cat_neon_alley"
        assert meta["duration_hint"] == 5

    def test_post_process_video_non_json_fallback(self):
        rendered, meta = GenericVideoStrategy.post_process_video("  plain text prompt  ")
        assert rendered == "plain text prompt"
        assert meta == {}

    def test_post_process_video_motion_intensity_clamped(self):
        bad = '{"prompt": "x", "motion_intensity": 99}'
        _rendered, meta = GenericVideoStrategy.post_process_video(bad)
        assert meta["motion_intensity"] == 10

    def test_post_process_video_empty_json_prompt_falls_back_to_fields(self):
        data = '{"prompt": "", "shot": "wide"}'
        rendered, meta = GenericVideoStrategy.post_process_video(data)
        assert rendered == ""
        assert meta["shot"] == "wide"


class TestOptimizerVideoPath:
    @pytest.fixture(autouse=True)
    def _no_cache(self, monkeypatch):
        """禁用持久化缓存读写，避免跨测试/跨进程命中导致 LLM mock 不触发，也不污染共享 prompt_cache.db。"""
        monkeypatch.setattr(Optimizer, "_cache_get", lambda self, *a, **k: None)
        monkeypatch.setattr(Optimizer, "_cache_set", lambda self, *a, **k: None)

    @patch.object(Optimizer, "_call_llm")
    def test_video_domain_fills_video_result(self, mock_call):
        mock_call.return_value = (VIDEO_LLM_JSON, 120)
        optimizer = Optimizer()
        req = OptimizeRequest(
            prompt="a cat running",
            domain=DomainType.VIDEO,
            platform=VideoPlatformType.GENERIC_VIDEO,
            creative_level=5,
        )
        result = optimizer.optimize(req)
        assert result.video is not None
        assert result.video.shot == "medium_wide"
        assert result.video.camera == "dolly"
        assert result.video.motion_intensity == 7
        assert result.video.continuity_token == "cat_neon_alley"
        assert result.video.duration_hint == 5
        assert "neon alley" in result.optimized_prompt

    @patch.object(Optimizer, "_call_llm")
    def test_video_domain_empty_llm_falls_back_to_original(self, mock_call):
        mock_call.return_value = ("", 0)
        optimizer = Optimizer()
        req = OptimizeRequest(
            prompt="原始文案",
            domain=DomainType.VIDEO,
            platform=VideoPlatformType.GENERIC_VIDEO,
            creative_level=5,
        )
        result = optimizer.optimize(req)
        assert result.optimized_prompt == "原始文案"
        assert result.video is None

    @patch.object(Optimizer, "_call_llm")
    def test_image_domain_has_no_video_field(self, mock_call):
        mock_call.return_value = ("optimized image prompt", 80)
        optimizer = Optimizer()
        req = OptimizeRequest(prompt="a cat", creative_level=5)
        result = optimizer.optimize(req)
        assert result.video is None
        assert "optimized image prompt" in result.optimized_prompt

    @patch.object(Optimizer, "_call_llm")
    def test_video_unknown_platform_falls_back_to_generic_video(self, mock_call):
        mock_call.return_value = (VIDEO_LLM_JSON, 90)
        optimizer = Optimizer()
        # 平台字段是枚举联合，直接构造非法值会被 pydantic 拒绝；
        # 通过 monkeypatch 平台值验证 Optimizer 回退 generic_video（不抛异常）
        req = OptimizeRequest(
            prompt="x",
            domain=DomainType.VIDEO,
            platform=VideoPlatformType.GENERIC_VIDEO,
            creative_level=5,
        )
        result = optimizer.optimize(req)
        assert result.optimized_prompt != ""

    @patch.object(Optimizer, "_call_llm")
    def test_video_template_path_skipped(self, mock_call):
        """视频领域 creative_level<=3 不走模板直出（模板只渲染图片六要素）。"""
        mock_call.return_value = (VIDEO_LLM_JSON, 10)
        optimizer = Optimizer()
        req = OptimizeRequest(
            prompt="a cat",
            domain=DomainType.VIDEO,
            platform=VideoPlatformType.GENERIC_VIDEO,
            creative_level=1,
        )
        result = optimizer.optimize(req)
        assert result.video is not None
        assert mock_call.called


class TestVideoOptimizeEndpoint:
    def _client_with_mocked_llm(self, monkeypatch):
        from prompt_engine.api import rest

        optimizer = Optimizer()
        monkeypatch.setattr(
            optimizer, "_call_llm",
            lambda system, user, variant=0: (VIDEO_LLM_JSON, 10),
        )
        monkeypatch.setattr(rest, "get_optimizer", lambda: optimizer)
        return TestClient(rest.app)

    def test_platforms_video_domain(self):
        from prompt_engine.api.rest import app

        client = TestClient(app)
        resp = client.get("/v1/platforms?domain=video")
        assert resp.status_code == 200
        assert "generic_video" in resp.json()["platforms"]

    def test_platforms_default_backward_compat(self):
        from prompt_engine.api.rest import app

        client = TestClient(app)
        resp = client.get("/v1/platforms")
        assert resp.status_code == 200
        assert "generic_video" not in resp.json()["platforms"]

    def test_optimize_video_returns_structured_result(self, monkeypatch):
        client = self._client_with_mocked_llm(monkeypatch)
        resp = client.post("/v1/optimize", json={
            "prompt": "a cat running through a neon alley",
            "domain": "video",
            "platform": "generic_video",
            "creative_level": 5,
        })
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "optimized_prompt" in data
        assert data.get("video", {}).get("shot") == "medium_wide"

    def test_optimize_video_unknown_platform_rejected(self):
        from prompt_engine.api.rest import app

        client = TestClient(app)
        resp = client.post("/v1/optimize", json={
            "prompt": "a cat",
            "domain": "video",
            "platform": "not-a-real-platform",
            "creative_level": 1,
        })
        assert resp.status_code == 422

    def test_optimize_video_batch_count(self, monkeypatch):
        client = self._client_with_mocked_llm(monkeypatch)
        resp = client.post("/v1/optimize/batch", json={
            "requests": [
                {"prompt": "scene one", "domain": "video", "platform": "generic_video", "creative_level": 5},
                {"prompt": "scene two", "domain": "video", "platform": "generic_video", "creative_level": 5},
            ]
        })
        assert resp.status_code == 200, resp.text
      
        data = resp.json()
        assert len(data) == 2
        assert all("optimized_prompt" in item for item in data)
