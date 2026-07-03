"""图片逆向工程测试"""
from unittest.mock import patch, MagicMock, PropertyMock
from prompt_engine.models import ReverseRequest, ReverseResult, PlatformType
from prompt_engine.optimizer import Optimizer


class TestReverseEngineer:
    @patch("prompt_engine.optimizer.BaseLLMProvider.from_config")
    def test_reverse_with_mock_provider(self, mock_from_config):
        """mock from_config 避免实际 LLM 调用"""
        mock_provider = MagicMock()
        mock_provider.chat.side_effect = [
            ("A cute tabby cat on a windowsill", 50),
            ("A fluffy tabby cat basking in warm afternoon sunlight...", 120),
        ]
        mock_provider.model_name = "gpt-4o"
        mock_from_config.return_value = mock_provider

        optimizer = Optimizer()
        req = ReverseRequest(
            image_url="https://example.com/cat.jpg",
            platform=PlatformType.MIDJOURNEY,
        )
        result = optimizer.reverse_engineer(req)
        assert isinstance(result, ReverseResult)
        assert result.duration_ms >= 0