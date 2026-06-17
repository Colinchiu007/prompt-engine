"""配置加载 — 支持 yaml 文件 + 环境变量覆盖"""
import os
from pathlib import Path
from typing import Optional
import yaml


_DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"


def _resolve_env(value):
    """递归解析字符串中的 ${ENV_VAR} 占位符"""
    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        env_name = value[2:-1]
        env_val = os.environ.get(env_name)
        if env_val is not None:
            return env_val  # 找到环境变量，返回实际值
    return value  # 非占位符或变量未设置，原样返回


def _resolve_env_recursive(obj):
    """递归处理嵌套结构中的环境变量"""
    if isinstance(obj, dict):
        return {k: _resolve_env_recursive(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_resolve_env_recursive(v) for v in obj]
    return _resolve_env(obj)


def load_config(path: Optional[str] = None) -> dict:
    """加载配置，默认读取项目根目录 config.yaml"""
    config_path = Path(path) if path else _DEFAULT_CONFIG_PATH
    if not config_path.exists():
        raise FileNotFoundError(f"配置文件不存在: {config_path}")
    with open(config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return _resolve_env_recursive(raw)
