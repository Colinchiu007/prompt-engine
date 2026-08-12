"""独立视频引擎配置（config_video.yaml + 环境变量覆盖）。

与图片引擎 config 解耦；LLM provider 通过环境变量 VIDEO_LLM_PROVIDER/MODEL/API_KEY 或
config_video.yaml 指定（支持 minimax/openai_compat/gemini 语义，实现见 llm/）。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any


DEFAULT_CONFIG: dict[str, Any] = {
    "server": {"port": 8020, "host": "0.0.0.0"},
    "knowledge": {
        "enabled": True,
        "persist_dir": "video_prompts_db",
        "retrieval": {"top_k": 3},
    },
    "llm": {
        "provider": "openai_compat",
        "model": "",
        "api_key": "",
        "base_url": "",
        "timeout": 60,
    },
    "optimizer": {
        "cache_size": 512,
        "max_retries": 2,
    },
}


def _load_yaml(path: Path) -> dict:
    import yaml
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def load_config(config_path: str | None = None) -> dict:
    """加载配置：默认值 → config_video.yaml（若存在）→ 环境变量覆盖。"""
    cfg = {k: dict(v) for k, v in DEFAULT_CONFIG.items()}

    path = Path(config_path) if config_path else Path(__file__).parent.parent / "config_video.yaml"
    file_cfg = _load_yaml(path)
    for section, values in file_cfg.items():
        if isinstance(values, dict) and section in cfg:
            cfg[section].update({k: v for k, v in values.items() if v is not None})
        else:
            cfg[section] = values

    # 环境变量覆盖（视频引擎前缀 VIDEO_）
    env = os.environ
    if env.get("VIDEO_LLM_PROVIDER"):
        cfg["llm"]["provider"] = env["VIDEO_LLM_PROVIDER"]
    if env.get("VIDEO_LLM_MODEL"):
        cfg["llm"]["model"] = env["VIDEO_LLM_MODEL"]
    if env.get("VIDEO_LLM_API_KEY"):
        cfg["llm"]["api_key"] = env["VIDEO_LLM_API_KEY"]
    if env.get("VIDEO_LLM_BASE_URL"):
        cfg["llm"]["base_url"] = env["VIDEO_LLM_BASE_URL"]
    if env.get("VIDEO_ENGINE_PORT"):
        try:
            cfg["server"]["port"] = int(env["VIDEO_ENGINE_PORT"])
        except ValueError:
            pass
    return cfg
