"""v0.16.0 — 输入验证 + 短文本处理"""


class TestInputValidation:
    """F1: 输入验证."""

    def test_short_chinese_rejected(self):
        """短中文（< 3 字）应返回 400"""
        from fastapi.testclient import TestClient
        from prompt_engine.api.rest import app
        client = TestClient(app)
        resp = client.post("/v1/optimize", json={
            "prompt": "好吧", "platform": "midjourney"
        })
        assert resp.status_code == 400, f"Got {resp.status_code}: {resp.text[:100]}"
        data = resp.json()
        assert "detail" in data

    def test_single_char_chinese_rejected(self):
        """单个中文字应返回 400"""
        from fastapi.testclient import TestClient
        from prompt_engine.api.rest import app
        client = TestClient(app)
        resp = client.post("/v1/optimize", json={
            "prompt": "好", "platform": "midjourney"
        })
        assert resp.status_code == 400

    def test_short_english_accepted(self):
        """短英文（2 词）应正常处理"""
        from fastapi.testclient import TestClient
        from prompt_engine.api.rest import app
        client = TestClient(app)
        resp = client.post("/v1/optimize", json={
            "prompt": "a cat", "platform": "midjourney"
        })
        # 应通过验证（非 400）
        assert resp.status_code != 400

    def test_detailed_chinese_accepted(self):
        """详细中文（≥ 5 字）应通过"""
        from fastapi.testclient import TestClient
        from prompt_engine.api.rest import app
        client = TestClient(app)
        resp = client.post("/v1/optimize", json={
            "prompt": "一只威严的猫", "platform": "midjourney"
        })
        assert resp.status_code != 400

    def test_empty_prompt_rejected(self):
        """空 prompt 应返回 422"""
        from fastapi.testclient import TestClient
        from prompt_engine.api.rest import app
        client = TestClient(app)
        resp = client.post("/v1/optimize", json={
            "prompt": "", "platform": "midjourney"
        })
        assert resp.status_code in (400, 422)

    def test_nonsense_chinese_rejected(self):
        """无意义中文短文本应返回 400"""
        from fastapi.testclient import TestClient
        from prompt_engine.api.rest import app
        client = TestClient(app)
        for short in ["嗯", "哦", "嗯嗯", "好的"]:
            resp = client.post("/v1/optimize", json={
                "prompt": short, "platform": "midjourney"
            })
            assert resp.status_code == 400, f"'{short}' should be rejected, got {resp.status_code}"
