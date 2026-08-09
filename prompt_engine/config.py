"""配置加载 — 支持 yaml 文件 + 环境变量覆盖"""
import os
from pathlib import Path
from typing import Optional
import yaml

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None


_DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"

# 项目根 .env：桌面 Bridge 启动时不注入 LLM Key（BasePythonBridge 只透传宿主 env），
# 引擎必须在解析环境占位符前自行加载，否则会以字面量占位符当 key 调用供应商
# （MiniMax 401 "Please carry the API secret key ... (1004)"）。
_ENV_FILE = Path(__file__).parent.parent / ".env"


def _ensure_env_loaded() -> None:
    """启动时加载项目根 .env（已存在的进程环境变量优先，不覆盖）。"""
    if load_dotenv is None:
        return
    load_dotenv(_ENV_FILE, override=False)

_PROVIDER_ENV_OVERRIDES = {
    "ai_router": {
        "api_key": ("AI_ROUTER_PROJECT_KEY", str),
        "base_url": ("AI_ROUTER_BASE_URL", str),
        "model": ("AI_ROUTER_MODEL", str),
    },
    "minimax": {
        "api_key": ("MINIMAX_API_KEY", str),
        "base_url": ("MINIMAX_BASE_URL", str),
        "model": ("MINIMAX_MODEL", str),
        "max_tokens": ("MINIMAX_MAX_TOKENS", int),
        "timeout": ("MINIMAX_TIMEOUT", int),
    },
    "openai_compat": {
        "api_key": ("OPENAI_COMPAT_API_KEY", str),
        "base_url": ("OPENAI_COMPAT_BASE_URL", str),
        "model": ("OPENAI_COMPAT_MODEL", str),
        "timeout": ("OPENAI_COMPAT_TIMEOUT", int),
    },
    "xfyun": {
        "api_key": ("XFYUN_API_KEY", str),
        "base_url": ("XFYUN_BASE_URL", str),
        "model": ("XFYUN_MODEL", str),
    },
}


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


def _apply_runtime_overrides(config: dict) -> dict:
    """仅覆盖当前选中的 Provider，避免无关环境变量污染其他配置。"""
    llm = config.setdefault("llm", {})
    provider = os.environ.get("LLM_PROVIDER")
    if provider:
        llm["provider"] = provider.strip().lower()

    selected_provider = llm.get("provider")
    if isinstance(selected_provider, str):
        selected_provider = selected_provider.strip().lower()
        llm["provider"] = selected_provider
    env_fields = _PROVIDER_ENV_OVERRIDES.get(selected_provider)
    if not env_fields:
        return config

    provider_config = dict(llm.get(selected_provider) or {})
    for field, (env_name, converter) in env_fields.items():
        value = os.environ.get(env_name)
        if value:
            try:
                provider_config[field] = converter(value)
            except ValueError as exc:
                raise ValueError(f"环境变量 {env_name} 的值无效: {value}") from exc
    if selected_provider == "ai_router":
        provider_config.setdefault("model", "auto")
    llm[selected_provider] = provider_config
    return config


def load_config(path: Optional[str] = None) -> dict:
    """加载配置，默认读取项目根目录 config.yaml"""
    _ensure_env_loaded()
    configured_path = path or os.environ.get("CONFIG_PATH")
    config_path = Path(configured_path) if configured_path else _DEFAULT_CONFIG_PATH
    if not config_path.exists():
        raise FileNotFoundError(f"配置文件不存在: {config_path}")
    with open(config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return _apply_runtime_overrides(_resolve_env_recursive(raw))
