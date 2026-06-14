"""v0.13.0 — 文档国际化 + PyPI 发布准备"""


class TestReadmeEnglish:
    """F1: README 英文版."""

    def test_readme_en_exists(self):
        """README.en.md 必须存在"""
        import os
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "README.en.md")
        assert os.path.exists(path), "README.en.md not found"

    def test_readme_en_has_english_content(self):
        """README.en.md 必须是英文内容"""
        import os
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "README.en.md")
        if not os.path.exists(path):
            return
        with open(path, encoding="utf-8") as f:
            content = f.read()
        # 检查英文特征
        assert "Prompt Engine" in content, "Should mention Prompt Engine"
        assert "Quick" in content or "Installation" in content
        assert "MIT" in content or "License" in content


class TestPyPIConfig:
    """F2: PyPI 发布配置."""

    def test_pyproject_has_pypi_name(self):
        """pyproject.toml 有 name/version 字段"""
        import os
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "pyproject.toml")
        assert os.path.exists(path)
        with open(path, encoding="utf-8") as f:
            content = f.read()
        assert "[project]" in content
        assert "name" in content
        assert "version" in content
        assert "MIT" in content or "license" in content

    def test_pypi_classifiers(self):
        """PyPI classifiers 应包含 Development Status"""
        import os
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "pyproject.toml")
        with open(path, encoding="utf-8") as f:
            content = f.read()
        if "classifiers" in content:
            assert "Development Status" in content


class TestGitHubBadge:
    """F3: GitHub Actions 徽章."""

    def test_readme_has_badge(self):
        """README.md 顶部应有徽章"""
        import os
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "README.md")
        with open(path, encoding="utf-8") as f:
            content = f.read()
        assert "badge.svg" in content or "badge" in content