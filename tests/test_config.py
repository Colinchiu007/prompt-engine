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
        assert cfg["llm"]["provider"] in ("openai_compat", "xfyun", "minimax")
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