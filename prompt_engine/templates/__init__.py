"""风格模板加载器"""
from pathlib import Path
import yaml

_TEMPLATES_DIR = Path(__file__).parent
_STYLES: dict | None = None


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
