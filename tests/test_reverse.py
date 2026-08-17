"""图片逆向工程测试"""
from unittest.mock import MagicMock
from prompt_engine.models import ReverseRequest, ReverseResult, PlatformType
from prompt_engine.optimizer import Optimizer


class TestReverseEngineer:
    def test_reverse_with_caller_provider(self):
        """逆向工程只使用调用方传入的 provider。"""
        mock_provider = MagicMock()
        mock_provider.chat.side_effect = [
            ("A cute tabby cat on a windowsill", 50),
            ("A fluffy tabby cat basking in warm afternoon sunlight...", 120),
        ]
        mock_provider.model_name = "gpt-4o"
        optimizer = Optimizer()
        req = ReverseRequest(
            image_url="https://example.com/cat.jpg",
            platform=PlatformType.MIDJOURNEY,
            llm={"provider": "openai_compat", "model": "gpt-4o", "api_key": "test-key"},
        )
        result = optimizer.reverse_engineer(req, provider=mock_provider)
        assert isinstance(result, ReverseResult)
        assert result.duration_ms >= 0
