"""v0.14.0 — 产品使用说明文档测试"""


class TestManual:
    """MANUAL.md 完整性测试."""

    def test_manual_exists(self):
        """MANUAL.md 必须存在"""
        import os
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs", "MANUAL.md")
        assert os.path.exists(path), "MANUAL.md not found"

    def test_manual_has_minimum_length(self):
        """MANUAL.md 应 >= 3000 字"""
        import os
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs", "MANUAL.md")
        with open(path, encoding="utf-8") as f:
            content = f.read()
        assert len(content) >= 3000, f"Only {len(content)} chars"

    def test_manual_covers_web(self):
        """MANUAL.md 应覆盖 Web 使用"""
        import os
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs", "MANUAL.md")
        with open(path, encoding="utf-8") as f:
            content = f.read()
        assert "工作台" in content or "Workbench" in content
        assert "数据看板" in content or "Dashboard" in content
        assert "配置" in content or "Settings" in content

    def test_manual_covers_cli(self):
        """MANUAL.md 应覆盖 CLI"""
        import os
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs", "MANUAL.md")
        with open(path, encoding="utf-8") as f:
            content = f.read()
        assert "optimize" in content or "CLI" in content

    def test_manual_covers_api(self):
        """MANUAL.md 应覆盖 API"""
        import os
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs", "MANUAL.md")
        with open(path, encoding="utf-8") as f:
            content = f.read()
        assert "/v1/optimize" in content

    def test_manual_has_quick_start(self):
        """MANUAL.md 应有快速开始"""
        import os
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs", "MANUAL.md")
        with open(path, encoding="utf-8") as f:
            content = f.read()
        assert "快速开始" in content or "Quick Start" in content

    def test_manual_has_toc(self):
        """MANUAL.md 应有目录"""
        import os
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs", "MANUAL.md")
        with open(path, encoding="utf-8") as f:
            content = f.read()
        assert "目录" in content or "Table of Contents" in content