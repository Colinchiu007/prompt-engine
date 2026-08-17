import pytest


@pytest.mark.asyncio
async def test_service_fails_closed_without_caller_llm(monkeypatch):
    from prompt_engine.services import prompt_service

    monkeypatch.setenv("OPENAI_API_KEY", "must-not-be-used")
    result = await prompt_service.optimize_prompt("一座古城")

    assert result.prompts == []
    assert "llm" in (result.error or "")


@pytest.mark.asyncio
async def test_service_passes_caller_llm_to_optimizer(monkeypatch):
    from prompt_engine.services import prompt_service
    from prompt_engine.models import OptimizeResult

    captured = {}

    class FakeProvider:
        model_name = "SenseNova-Test"

    class FakeOptimizer:
        def optimize(self, request, provider=None, provider_id=""):
            captured["request"] = request
            captured["provider"] = provider
            captured["provider_id"] = provider_id
            return OptimizeResult(
                optimized_prompt="A cinematic ancient city",
                platform=request.platform,
                model_used=provider.model_name,
                strategy_used="llm",
            )

    monkeypatch.setattr(prompt_service, "Optimizer", FakeOptimizer)
    monkeypatch.setattr(
        prompt_service.BaseLLMProvider,
        "from_llm_object",
        classmethod(lambda cls, llm: FakeProvider()),
    )

    llm = {
        "provider": "sensenova",
        "model": "SenseNova-Test",
        "base_url": "https://llm.example/v1",
        "api_key": "caller-key",
    }
    llm["caller"] = "test-product"
    result = await prompt_service.optimize_prompt("一座古城", llm=llm)

    assert result.prompts == ["A cinematic ancient city"]
    assert captured["request"].llm is not None
    assert captured["request"].llm.model == "SenseNova-Test"
    assert captured["request"].llm.caller == "test-product"
    assert captured["provider"].model_name == "SenseNova-Test"
    assert "caller-key" not in captured["provider_id"]


@pytest.mark.asyncio
async def test_service_batch_uses_same_caller_bind(monkeypatch):
    from prompt_engine.services import prompt_service

    seen = []

    class FakeProvider:
        model_name = "SenseNova-Test"

    class FakeOptimizer:
        def optimize(self, request, provider=None, provider_id=""):
            seen.append((request.prompt, request.llm.caller, provider.model_name))
            return type("Result", (), {
                "optimized_prompt": request.prompt + " optimized",
                "error": None,
            })()

    monkeypatch.setattr(prompt_service, "Optimizer", FakeOptimizer)
    monkeypatch.setattr(
        prompt_service.BaseLLMProvider,
        "from_llm_object",
        classmethod(lambda cls, llm: FakeProvider()),
    )

    result = await prompt_service.optimize_prompts_batch(
        [{"text": "第一场"}, {"text": "第二场"}],
        llm={
            "provider": "sensenova",
            "model": "SenseNova-Test",
            "api_key": "caller-key",
            "caller": "test-product",
        },
    )

    assert result.prompts == ["第一场 optimized", "第二场 optimized"]
    assert seen == [
        ("第一场", "test-product", "SenseNova-Test"),
        ("第二场", "test-product", "SenseNova-Test"),
    ]
