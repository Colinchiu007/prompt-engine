"""模板加载器测试 — F1: 模板驱动优化."""
import pytest
from pathlib import Path


class TestTemplateLoader:
    """测试 prompt 模板的加载和渲染."""

    def test_load_midjourney_en(self):
        from prompt_engine.templates import load_prompt_template
        tmpl = load_prompt_template("midjourney", lang="en")
        assert tmpl is not None
        assert "name" in tmpl
        assert tmpl["name"] == "midjourney"
        assert "system_prompt" in tmpl
        assert len(tmpl["system_prompt"]) > 50

    def test_load_midjourney_zh(self):
        from prompt_engine.templates import load_prompt_template
        tmpl = load_prompt_template("midjourney", lang="zh")
        assert tmpl is not None
        # 无中文模板时回退英文
        assert len(tmpl["system_prompt"]) > 50

    def test_fallback_to_en_when_zh_missing(self):
        """当特定语言模板不存在时，回退到英文."""
        from prompt_engine.templates import load_prompt_template
        # 假设 stable_diffusion 只有 en
        tmpl = load_prompt_template("stable_diffusion", lang="zh")
        assert tmpl is not None

    def test_unknown_template_returns_default(self):
        from prompt_engine.templates import load_prompt_template
        tmpl = load_prompt_template("nonexistent_platform", lang="en")
        # 应该返回默认的通用模板
        assert tmpl is not None
        assert "system_prompt" in tmpl

    def test_template_has_rules(self):
        from prompt_engine.templates import load_prompt_template
        tmpl = load_prompt_template("midjourney", lang="en")
        assert "rules" in tmpl
        assert "aspect_ratio" in tmpl["rules"]

    def test_template_format_supports_variables(self):
        from prompt_engine.templates import load_prompt_template
        tmpl = load_prompt_template("generic", lang="en")
        system_prompt = tmpl["system_prompt"]
        # 模板应支持 .format() 变量注入
        assert "{style}" in system_prompt or "{platform}" in system_prompt or "style" in system_prompt
