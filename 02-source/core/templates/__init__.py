"""风格模板加载器 — 支持标准 yaml 模板 + prompt 优化模板"""
from pathlib import Path
from typing import Optional
import yaml

_TEMPLATES_DIR = Path(__file__).parent
_STYLES: dict | None = None
_PROMPT_TEMPLATES: dict[str, dict[str, dict]] = {}  # {name: {lang: data}}


def load_styles() -> dict:
    """加载 styles.yaml 风格模板"""
    global _STYLES
    if _STYLES is None:
        path = _TEMPLATES_DIR / "styles.yaml"
        with open(path, "r", encoding="utf-8") as f:
            _STYLES = yaml.safe_load(f)
    return _STYLES


def get_style_template(style_name: str) -> dict | None:
    """获取指定风格的模板"""
    styles = load_styles()
    return styles.get(style_name)


def list_style_names() -> list[str]:
    """列出所有可用风格名称"""
    return list(load_styles().keys())


def load_prompt_template(name: str, lang: str = "en") -> dict:
    """加载 prompt 优化模板（支持 EN/ZH 双语，自动回退）.

    Args:
        name: 模板名称（如 "midjourney", "stable_diffusion"）
        lang: 语言代码 ("en" / "zh")

    Returns:
        模板字典，包含 system_prompt, rules 等字段
    """
    # 先检查缓存
    if name in _PROMPT_TEMPLATES and lang in _PROMPT_TEMPLATES[name]:
        return _PROMPT_TEMPLATES[name][lang]

    prompts_dir = _TEMPLATES_DIR / "prompts" / name
    if not prompts_dir.exists():
        # 不存在该平台模板，返回通用默认模板
        return _get_default_template(lang)

    # 尝试加载指定语言
    lang_file = prompts_dir / f"{lang}.yaml"
    if lang_file.exists():
        with open(lang_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if name not in _PROMPT_TEMPLATES:
            _PROMPT_TEMPLATES[name] = {}
        _PROMPT_TEMPLATES[name][lang] = data
        return data

    # 回退到英文
    en_file = prompts_dir / "en.yaml"
    if en_file.exists():
        with open(en_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if name not in _PROMPT_TEMPLATES:
            _PROMPT_TEMPLATES[name] = {}
        _PROMPT_TEMPLATES[name][lang] = data
        return data

    return _get_default_template(lang)


def _get_default_template(lang: str = "en") -> dict:
    """返回通用默认模板。"""
    prompts_dir = _TEMPLATES_DIR / "prompts" / "generic"
    if prompts_dir.exists():
        lang_file = prompts_dir / f"{lang}.yaml"
        if not lang_file.exists():
            lang_file = prompts_dir / "en.yaml"
        if lang_file.exists():
            with open(lang_file, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)

    # 硬编码兜底
    return {
        "name": "generic",
        "language": lang,
        "description": "Generic prompt optimization template",
        "system_prompt": "你是一位 AI 图片生成提示词优化专家。请将用户的描述优化为高质量 prompt。\n风格：{style}\n创意等级：{creative_level}",
        "rules": {},
    }
