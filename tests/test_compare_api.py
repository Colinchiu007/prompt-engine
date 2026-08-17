"""对比验证 API（/v1/compare/*）测试

覆盖：
- split：文案校验（空 / 超 6000 字）、分句代理成功、分句服务不可用（503）
- prompt：调用方 llm 必填、环境 Key 不回退、<think> 剥离、剥离后为空（502 可重试）
- images：独立图片 Key（无 key / 成功 / 空结果 / 鉴权错误）

铁律：全部 mock 隔离，不依赖真实 API Key / 网络 / 分句服务。
"""
import pytest
from fastapi.testclient import TestClient

from prompt_engine.api.minimax_client import MinimaxImageError


@pytest.fixture
def client():
    from prompt_engine.api.rest import app
    return TestClient(app)


# ── POST /v1/compare/split ─────────────────────────────

class TestCompareSplit:
    def test_split_empty_text_rejected(self, client):
        resp = client.post("/v1/compare/split", json={"text": "   "})
        assert resp.status_code == 422

    def test_split_over_6000_rejected(self, client):
        resp = client.post("/v1/compare/split", json={"text": "字" * 6001})
        assert resp.status_code == 422
        assert "6000" in str(resp.json()["detail"])

    def test_split_proxies_splitter(self, client, monkeypatch):
        import httpx

        class FakeResp:
            status_code = 200
            def json(self):
                return {
                    "text_length": 30,
                    "language": "zh",
                    "tier_used": "tier3_rule",
                    "sentences": [
                        {"index": 0, "text": "第一句。", "language": "zh", "tier": "tier3_rule",
                         "confidence": 0.98, "char_count": 5},
                        {"index": 1, "text": "第二句。", "language": "zh", "tier": "tier3_rule",
                         "confidence": 0.95, "char_count": 5},
                    ],
                    "scenes": [],
                }

        captured = {}
        def fake_post(url, json=None, timeout=None):
            captured["url"] = url
            captured["body"] = json
            return FakeResp()

        monkeypatch.setattr(httpx, "post", fake_post)
        resp = client.post("/v1/compare/split", json={"text": "第一句。第二句。"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["sentences"]) == 2
        assert data["sentences"][0]["text"] == "第一句。"
        assert data["tier_used"] == "tier3_rule"
        assert "/v1/split" in captured["url"]
        assert captured["body"]["text"] == "第一句。第二句。"

    def test_split_splitter_unavailable(self, client, monkeypatch):
        import httpx

        def fake_post(url, json=None, timeout=None):
            raise httpx.ConnectError("connection refused")

        monkeypatch.setattr(httpx, "post", fake_post)
        resp = client.post("/v1/compare/split", json={"text": "测试文案"})
        assert resp.status_code == 503
        assert "smart-sentence-splitter" in resp.json()["detail"]

    def test_split_empty_result(self, client, monkeypatch):
        import httpx

        class FakeResp:
            status_code = 200
            def json(self):
                return {"text_length": 4, "sentences": [], "scenes": []}

        monkeypatch.setattr(httpx, "post", lambda *a, **k: FakeResp())
        resp = client.post("/v1/compare/split", json={"text": "测试文案"})
        assert resp.status_code == 422


# ── POST /v1/compare/prompt ────────────────────────────

class TestComparePrompt:
    @staticmethod
    def llm_payload():
        return {
            "provider": "sensenova",
            "model": "SenseNova-Test",
            "base_url": "https://llm.example/v1",
            "api_key": "caller-llm-key",
        }

    def test_prompt_requires_caller_llm_even_when_image_env_key_exists(self, client, monkeypatch):
        monkeypatch.setenv("MINIMAX_API_KEY", "image-only-key")
        resp = client.post("/v1/compare/prompt", json={"text": "一只猫"})
        assert resp.status_code == 422
        assert "llm" in str(resp.json()["detail"])

    def test_prompt_strips_think_blocks(self, client, monkeypatch):
        from prompt_engine.api import compare as compare_mod

        captured = {}

        class FakeProvider:
            model_name = "SenseNova-Test"

            def chat(self, messages):
                captured["messages"] = messages
                return "<think>推理过程</think>A majestic cat sitting on a velvet throne.", 12

        monkeypatch.setattr(
            compare_mod.BaseLLMProvider,
            "from_llm_object",
            classmethod(lambda cls, llm: (captured.setdefault("llm", llm), FakeProvider())[1]),
        )
        resp = client.post("/v1/compare/prompt", json={
            "text": "一只猫坐在天鹅绒王座上",
            "llm": self.llm_payload(),
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "<think>" not in data["prompt"]
        assert "majestic cat" in data["prompt"].lower()
        assert captured["llm"].provider == "sensenova"
        assert captured["llm"].model == "SenseNova-Test"
        assert captured["llm"].api_key == "caller-llm-key"
        assert data["model"] == "SenseNova-Test"

    def test_prompt_empty_after_strip_retryable(self, client, monkeypatch):
        from prompt_engine.api import compare as compare_mod

        class FakeProvider:
            model_name = "SenseNova-Test"

            def chat(self, messages):
                return "<think>only thinking</think>", 12

        monkeypatch.setattr(
            compare_mod.BaseLLMProvider,
            "from_llm_object",
            classmethod(lambda cls, llm: FakeProvider()),
        )
        resp = client.post("/v1/compare/prompt", json={
            "text": "测试",
            "llm": self.llm_payload(),
        })
        assert resp.status_code == 502
        assert "空" in resp.json()["detail"]

    def test_prompt_does_not_read_minimax_env_as_text_llm(self, client, monkeypatch):
        from prompt_engine.api import compare as compare_mod

        monkeypatch.setenv("MINIMAX_API_KEY", "image-only-key")
        called = {"value": False}

        def fail_if_called(cls, llm):
            called["value"] = True
            raise AssertionError("provider must not be built without caller llm")

        monkeypatch.setattr(
            compare_mod.BaseLLMProvider,
            "from_llm_object",
            classmethod(fail_if_called),
        )
        resp = client.post("/v1/compare/prompt", json={"text": "测试"})
        assert resp.status_code == 422
        assert called["value"] is False


# ── POST /v1/compare/images ────────────────────────────

class TestCompareImages:
    def test_images_requires_key(self, client, monkeypatch):
        monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
        resp = client.post("/v1/compare/images", json={"prompt": "a cat"})
        assert resp.status_code == 400

    def test_images_returns_two_urls(self, client, monkeypatch):
        from prompt_engine.api import compare as compare_mod

        monkeypatch.setattr(
            compare_mod, "generate_minimax_images",
            lambda **kw: {"urls": ["https://img1.example/a.png", "https://img2.example/b.png"],
                          "model": "image-01", "count": 2})
        resp = client.post("/v1/compare/images", json={
            "prompt": "a cat",
            "api_key": "test-key-123",
            "n": 2,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2
        assert len(data["urls"]) == 2
        assert data["model"] == "image-01"

    def test_images_empty_result_maps_422(self, client, monkeypatch):
        from prompt_engine.api import compare as compare_mod

        def boom(**kw):
            raise MinimaxImageError("MiniMax 返回了空结果", error_type="empty_result", retryable=True)

        monkeypatch.setattr(compare_mod, "generate_minimax_images", boom)
        resp = client.post("/v1/compare/images", json={
            "prompt": "a cat",
            "api_key": "test-key-123",
        })
        assert resp.status_code == 422
        assert "空结果" in resp.json()["detail"]

    def test_images_auth_error_maps_400(self, client, monkeypatch):
        from prompt_engine.api import compare as compare_mod

        def boom(**kw):
            raise MinimaxImageError("鉴权失败", error_type="auth", retryable=False)

        monkeypatch.setattr(compare_mod, "generate_minimax_images", boom)
        resp = client.post("/v1/compare/images", json={
            "prompt": "a cat",
            "api_key": "bad-key",
        })
        assert resp.status_code == 400


# ── 共享助手 minimax_client ────────────────────────────

class TestMinimaxClient:
    def test_parse_aspect_ratio(self):
        from prompt_engine.api.minimax_client import parse_aspect_ratio
        assert parse_aspect_ratio("1024x1024") == "1:1"
        assert parse_aspect_ratio("1920x1080") == "16:9"
        assert parse_aspect_ratio("1080x1920") == "9:16"
        assert parse_aspect_ratio("1280x960") == "4:3"
        assert parse_aspect_ratio(None) is None

    def test_generate_images_requires_key(self):
        from prompt_engine.api.minimax_client import generate_minimax_images, MinimaxImageError
        with pytest.raises(MinimaxImageError) as ei:
            generate_minimax_images("a cat", "")
        assert ei.value.error_type == "invalid_config"

    def test_generate_images_invalid_n(self):
        from prompt_engine.api.minimax_client import generate_minimax_images, MinimaxImageError
        with pytest.raises(MinimaxImageError) as ei:
            generate_minimax_images("a cat", "k", n=99)
        assert "n 需在" in ei.value.message

    def test_generate_images_empty_result_raises(self, monkeypatch):
        import httpx
        from prompt_engine.api import minimax_client as mc

        class FakeResp:
            status_code = 200
            def json(self):
                return {"data": {"image_urls": []}, "base_resp": {"status_msg": "success"}}

        monkeypatch.setattr(httpx, "post", lambda *a, **k: FakeResp())
        with pytest.raises(MinimaxImageError) as ei:
            mc.generate_minimax_images("a cat", "k")
        assert ei.value.error_type == "empty_result"
        assert ei.value.retryable is True

    def test_generate_images_auth_maps_error(self, monkeypatch):
        import httpx
        from prompt_engine.api import minimax_client as mc

        class FakeResp:
            status_code = 401
            def json(self):
                return {"message": "unauthorized"}

        monkeypatch.setattr(httpx, "post", lambda *a, **k: FakeResp())
        with pytest.raises(MinimaxImageError) as ei:
            mc.generate_minimax_images("a cat", "bad-key")
        assert ei.value.error_type == "auth"
        assert ei.value.retryable is False# ── 修复后的补充覆盖 ─────────────────────────────────

class TestImagesErrorMapping:
    """MinimaxImageError 每种 error_type 的 HTTP 映射（PRD 12.6 错误表）。"""

    @pytest.mark.parametrize("error_type,expected_status", [
        ("auth", 400),
        ("rate_limit", 429),
        ("timeout", 504),
        ("network", 502),
        ("provider_error", 502),
        ("content_safety", 422),
        ("invalid_config", 422),
    ])
    def test_error_mapping(self, client, monkeypatch, error_type, expected_status):
        from prompt_engine.api import compare as compare_mod

        def boom(**kw):
            raise MinimaxImageError("boom-" + error_type, error_type=error_type, retryable=True)

        monkeypatch.setattr(compare_mod, "generate_minimax_images", boom)
        resp = client.post("/v1/compare/images", json={"prompt": "a cat", "api_key": "k"})
        assert resp.status_code == expected_status


class TestBaseUrlValidation:
    @pytest.mark.parametrize("bad_url", [
        "ftp://api.minimaxi.com/v1",          # 非 http(s)
        "http://user@api.minimaxi.com/v1",    # 凭证嵌入
        "http://127.0.0.1:8080/v1",           # 回环
        "http://localhost:8080/v1",           # 回环
        "http://192.168.1.10/v1",             # 私网
        "http://10.0.0.5/v1",                 # 私网
        "http://169.254.169.254/v1",          # 云 metadata
        "http://api.minimaxi.com/v1",         # 非回环明文 http
        "not a url",
    ])
    def test_rejects_bad_base_url(self, client, monkeypatch, bad_url):
        from prompt_engine.api import compare as compare_mod
        monkeypatch.setattr(compare_mod, "generate_minimax_images", lambda **kw: {"urls": ["x"], "count": 1, "model": "image-01"})
        resp = client.post("/v1/compare/images", json={
            "prompt": "a cat", "api_key": "k", "base_url": bad_url,
        })
        assert resp.status_code == 422

    def test_accepts_https_base_url(self, client, monkeypatch):
        from prompt_engine.api import compare as compare_mod
        monkeypatch.setattr(compare_mod, "generate_minimax_images", lambda **kw: {"urls": ["x"], "count": 1, "model": "image-01"})
        resp = client.post("/v1/compare/images", json={
            "prompt": "a cat", "api_key": "k", "base_url": "https://api.minimaxi.com/v1",
        })
        assert resp.status_code == 200


class TestCompareStatus:
    def test_status_reports_image_env_key_only(self, client, monkeypatch):
        monkeypatch.setenv("MINIMAX_API_KEY", "sk-test-123456")
        resp = client.get("/v1/compare/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_image_env_key"] is True
        assert data["text_llm_requires_caller_bind"] is True
        assert "splitter" in data

    def test_status_no_image_env_key(self, client, monkeypatch):
        monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
        resp = client.get("/v1/compare/status")
        assert resp.status_code == 200
        assert resp.json()["has_image_env_key"] is False


class TestPromptTruncation:
    def test_prompt_truncated_flag(self, client, monkeypatch):
        from prompt_engine.api import compare as compare_mod

        class FakeProvider:
            model_name = "SenseNova-Test"

            def chat(self, messages):
                return "word " * 5000, 12

        monkeypatch.setattr(
            compare_mod.BaseLLMProvider,
            "from_llm_object",
            classmethod(lambda cls, llm: FakeProvider()),
        )
        resp = client.post("/v1/compare/prompt", json={
            "text": "测试",
            "llm": TestComparePrompt.llm_payload(),
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["truncated"] is True
        assert len(data["prompt"]) <= 2000


class TestSplitLanguageEnum:
    def test_invalid_language_rejected(self, client):
        resp = client.post("/v1/compare/split", json={"text": "测试", "language": "xx"})
        assert resp.status_code == 422

    def test_invalid_mode_rejected(self, client):
        resp = client.post("/v1/compare/split", json={"text": "测试", "mode": "ultra"})
        assert resp.status_code == 422

# ── 场景层 / 字幕层透传 ────────────────────────────────

class TestCompareSplitSceneLayers:
    def test_split_proxies_scenes_with_subtitles(self, client, monkeypatch):
        """分句代理必须透传场景层（scenes）与字幕层（subtitles），供前端分层展示。"""
        import httpx

        class FakeResp:
            status_code = 200
            def json(self):
                return {
                    "text_length": 40,
                    "language": "zh",
                    "tier_used": "tier2_semantic",
                    "sentences": [{"index": 0, "text": "第一句。", "language": "zh", "tier": "t2", "confidence": 1.0, "char_count": 4}],
                    "scenes": [
                        {
                            "segment_id": 0,
                            "text": "第一句。第二句。",
                            "estimated_duration": 3.0,
                            "target_words": 8,
                            "subtitle_count": 2,
                            "subtitles": [
                                {"text": "第一句", "display_order": 0, "start_time": 0.0, "duration": 1.5, "parent_segment_id": 0},
                                {"text": "第二句", "display_order": 1, "start_time": 1.5, "duration": 1.5, "parent_segment_id": 0},
                            ],
                        }
                    ],
                }

        monkeypatch.setattr(httpx, "post", lambda *a, **k: FakeResp())
        resp = client.post("/v1/compare/split", json={"text": "第一句。第二句。"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["scenes"]) == 1
        scene = data["scenes"][0]
        assert scene["subtitle_count"] == 2
        assert "subtitles" in scene
        assert len(scene["subtitles"]) == 2
        assert scene["subtitles"][0]["text"] == "第一句"
        assert scene["subtitles"][0]["display_order"] == 0
        assert scene["subtitles"][0]["start_time"] == 0.0
        assert "duration" in scene["subtitles"][0]
        assert "parent_segment_id" in scene["subtitles"][0]
