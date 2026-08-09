"""配置系统测试"""
import os
import tempfile
from pathlib import Path
import yaml
import pytest
from prompt_engine.config import load_config, _resolve_env, _resolve_env_recursive


class TestResolveEnv:
    def test_literal_string(self):
        assert _resolve_env("hello") == "hello"

    def test_env_var(self):
        os.environ["_TEST_KEY"] = "sk-test123"
        assert _resolve_env("${_TEST_KEY}") == "sk-test123"

    def test_nonexistent_env_var(self):
        """环境变量不存在时保留占位符"""
        result = _resolve_env("${_DOES_NOT_EXIST_ABC123}")
        assert result == "${_DOES_NOT_EXIST_ABC123}"

    def test_normal_int(self):
        assert _resolve_env(42) == 42


class TestResolveEnvRecursive:
    def test_nested_dict(self):
        data = {
            "api_key": "${_TEST_KEY}",
            "nested": {"key": "${_TEST_KEY}"},
        }
        os.environ["_TEST_KEY"] = "sk-abc"
        result = _resolve_env_recursive(data)
        assert result["api_key"] == "sk-abc"
        assert result["nested"]["key"] == "sk-abc"

    def test_list(self):
        os.environ["_TEST_KEY"] = "val"
        data = {"keys": ["${_TEST_KEY}", "static"]}
        result = _resolve_env_recursive(data)
        assert result["keys"] == ["val", "static"]


class TestLoadConfig:
    def test_load_default_fields(self):
        """加载 config.yaml 验证关键字段存在"""
        cfg = load_config()
        assert "llm" in cfg
        assert "engine" in cfg
        assert "server" in cfg
        assert "platforms" in cfg
        assert cfg["llm"]["provider"] in ("ai_router", "openai_compat", "xfyun", "minimax")
        assert cfg["engine"]["default_platform"] == "generic"
        assert cfg["server"]["port"] == 8013

    def test_load_with_env_override(self):
        """写临时配置文件测试环境变量解析"""
        os.environ["_TEST_OPENAI_KEY"] = "sk-real-key"
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            yaml.dump({
                "llm": {
                    "provider": "openai_compat",
                    "openai_compat": {
                        "api_key": "${_TEST_OPENAI_KEY}",
                        "base_url": "https://test.com/v1",
                        "model": "gpt-4o",
                        "temperature": 0.7,
                        "max_tokens": 500,
                        "timeout": 15,
                    },
                },
                "engine": {"default_platform": "midjourney"},
                "server": {"host": "0.0.0.0", "port": 8080},
                "platforms": {"midjourney": {"enabled": True}},
            }, f)
            tmp_path = f.name

        try:
            cfg = load_config(tmp_path)
            assert cfg["llm"]["openai_compat"]["api_key"] == "sk-real-key"
            assert cfg["engine"]["default_platform"] == "midjourney"
            assert cfg["server"]["port"] == 8080
        finally:
            os.unlink(tmp_path)

    def test_config_not_found(self):
        with pytest.raises(FileNotFoundError):
            load_config("/nonexistent/path/config.yaml")

    def test_config_path_environment_variable(self, monkeypatch):
        """未传显式路径时应读取 CONFIG_PATH。"""
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".yaml",
            dir=Path(__file__).parent,
            delete=False,
            encoding="utf-8",
        ) as handle:
            yaml.safe_dump(
                {
                    "llm": {"provider": "minimax", "minimax": {}},
                    "engine": {"default_platform": "custom"},
                },
                handle,
            )
            config_path = handle.name
        monkeypatch.setenv("CONFIG_PATH", config_path)
        monkeypatch.delenv("LLM_PROVIDER", raising=False)

        try:
            cfg = load_config()
        finally:
            os.unlink(config_path)

        assert cfg["engine"]["default_platform"] == "custom"

    def test_minimax_environment_overrides_selected_profile(self, monkeypatch):
        """MiniMax 示例环境变量应覆盖默认配置并保留数值类型。"""
        monkeypatch.setenv("LLM_PROVIDER", "minimax")
        monkeypatch.setenv("MINIMAX_API_KEY", "minimax-test-key")
        monkeypatch.setenv("MINIMAX_BASE_URL", "https://minimax.example/v1")
        monkeypatch.setenv("MINIMAX_MODEL", "MiniMax-Test")
        monkeypatch.setenv("MINIMAX_TIMEOUT", "45")

        cfg = load_config()

        assert cfg["llm"]["minimax"] == {
            "api_key": "minimax-test-key",
            "base_url": "https://minimax.example/v1",
            "model": "MiniMax-Test",
            "temperature": 0.7,
            "max_tokens": 1500,
            "timeout": 45,
        }

    def test_openai_compat_environment_overrides_selected_profile(self, monkeypatch):
        """OpenAI 兼容示例环境变量应覆盖对应配置。"""
        monkeypatch.setenv("LLM_PROVIDER", "openai_compat")
        monkeypatch.setenv("OPENAI_COMPAT_API_KEY", "openai-test-key")
        monkeypatch.setenv("OPENAI_COMPAT_BASE_URL", "https://openai.example/v1")
        monkeypatch.setenv("OPENAI_COMPAT_MODEL", "openai-test-model")
        monkeypatch.setenv("OPENAI_COMPAT_TIMEOUT", "30")

        cfg = load_config()

        assert cfg["llm"]["openai_compat"] == {
            "api_key": "openai-test-key",
            "base_url": "https://openai.example/v1",
            "model": "openai-test-model",
            "temperature": 0.7,
            "max_tokens": 500,
            "timeout": 30,
        }

    def test_provider_name_environment_override_is_normalized(self, monkeypatch):
        """Provider 名称应兼容环境变量中常见的空格和大小写。"""
        monkeypatch.setenv("LLM_PROVIDER", " AI_ROUTER ")
        monkeypatch.setenv("AI_ROUTER_PROJECT_KEY", "router-test-key")

        cfg = load_config()

        assert cfg["llm"]["provider"] == "ai_router"
        assert cfg["llm"]["ai_router"]["api_key"] == "router-test-key"

class TestMinimaxMaxTokens:
    def test_minimax_default_max_tokens_from_config(self, monkeypatch):
        """config.yaml 默认 max_tokens=1500（推理模型预算，避免 <think> 耗尽输出）"""
        monkeypatch.delenv("MINIMAX_MAX_TOKENS", raising=False)
        cfg = load_config()
        assert cfg["llm"]["minimax"]["max_tokens"] == 1500

    def test_minimax_max_tokens_env_override(self, monkeypatch):
        """MINIMAX_MAX_TOKENS 环境变量可覆盖 config.yaml"""
        monkeypatch.setenv("MINIMAX_MAX_TOKENS", "2000")
        cfg = load_config()
        assert cfg["llm"]["minimax"]["max_tokens"] == 2000
