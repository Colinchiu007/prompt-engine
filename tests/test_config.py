"""引擎运行配置测试。"""

import tempfile
from pathlib import Path

import pytest
import yaml

from prompt_engine.config import load_config, _resolve_env, _resolve_env_recursive


class TestResolveEnv:
    def test_literal_string(self):
        assert _resolve_env("hello") == "hello"

    def test_env_var(self, monkeypatch):
        monkeypatch.setenv("_TEST_KEY", "sk-test123")
        assert _resolve_env("$" + "{_TEST_KEY}") == "sk-test123"

    def test_nonexistent_env_var(self):
        value = "$" + "{_DOES_NOT_EXIST_ABC123}"
        assert _resolve_env(value) == value

    def test_nested_dict(self, monkeypatch):
        monkeypatch.setenv("_TEST_KEY", "sk-abc")
        value = "$" + "{_TEST_KEY}"
        result = _resolve_env_recursive({"api_key": value, "nested": {"key": value}})
        assert result == {"api_key": "sk-abc", "nested": {"key": "sk-abc"}}


class TestLoadConfig:
    def test_load_default_fields_and_no_llm_section(self):
        cfg = load_config()
        assert "llm" not in cfg
        assert cfg["engine"]["default_platform"] == "generic"
        assert cfg["server"]["port"] == 8013
        assert "platforms" in cfg

    def test_top_level_llm_section_is_rejected(self, tmp_path):
        config_path = tmp_path / "legacy-config.yaml"
        config_path.write_text(
            yaml.safe_dump({
                "llm": {"provider": "minimax", "minimax": {"api_key": "must-not-be-used"}},
                "engine": {"default_platform": "midjourney"},
                "server": {"port": 8080},
            }),
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="不支持顶层 llm"):
            load_config(str(config_path))

    def test_load_resolves_non_llm_environment_values(self, monkeypatch):
        monkeypatch.setenv("_TEST_HOST", "127.0.0.1")
        value = "$" + "{_TEST_HOST}"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as handle:
            yaml.safe_dump({"server": {"host": value, "port": 8080}}, handle)
            config_path = handle.name
        try:
            cfg = load_config(config_path)
        finally:
            Path(config_path).unlink()
        assert cfg["server"]["host"] == "127.0.0.1"
        assert cfg["server"]["port"] == 8080

    def test_config_path_environment_variable(self, monkeypatch, tmp_path):
        config_path = tmp_path / "custom.yaml"
        config_path.write_text(yaml.safe_dump({"engine": {"default_platform": "custom"}}), encoding="utf-8")
        monkeypatch.setenv("CONFIG_PATH", str(config_path))
        cfg = load_config()
        assert cfg["engine"]["default_platform"] == "custom"

    def test_config_not_found(self):
        with pytest.raises(FileNotFoundError):
            load_config("/nonexistent/path/config.yaml")
