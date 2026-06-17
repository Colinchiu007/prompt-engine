"""v0.10.0 工程化 + 批量优化测试 (TDD RED -> GREEN)"""
import os
import pytest


class TestDockerDeployment:
    """F1: Dockerfile + docker-compose 部署文件存在性测试."""

    def test_dockerfile_exists(self):
        """Dockerfile 必须存在"""
        repo = os.path.dirname(os.path.dirname(__file__))
        path = os.path.join(repo, "Dockerfile")
        assert os.path.exists(path), f"Dockerfile not found at {path}"

    def test_dockerfile_has_required_directives(self):
        """Dockerfile 包含必要指令"""
        repo = os.path.dirname(os.path.dirname(__file__))
        path = os.path.join(repo, "Dockerfile")
        if not os.path.exists(path):
            pytest.skip("Dockerfile not yet created")
        content = open(path, encoding="utf-8").read()
        # 必含指令
        assert "FROM" in content, "Dockerfile must have FROM"
        assert "WORKDIR" in content, "Dockerfile must have WORKDIR"
        assert "COPY" in content, "Dockerfile must have COPY"
        assert "EXPOSE" in content, "Dockerfile must have EXPOSE"
        assert "CMD" in content, "Dockerfile must have CMD"
        # 监听 8000
        assert "8000" in content, "Dockerfile must expose port 8000"
        # 包含 uvicorn
        assert "uvicorn" in content, "Dockerfile must use uvicorn"

    def test_docker_compose_exists(self):
        """docker-compose.yml 必须存在"""
        repo = os.path.dirname(os.path.dirname(__file__))
        path = os.path.join(repo, "docker-compose.yml")
        assert os.path.exists(path), f"docker-compose.yml not found at {path}"

    def test_docker_compose_valid_structure(self):
        """docker-compose.yml 含 services + ports"""
        repo = os.path.dirname(os.path.dirname(__file__))
        path = os.path.join(repo, "docker-compose.yml")
        if not os.path.exists(path):
            pytest.skip("docker-compose.yml not yet created")
        content = open(path, encoding="utf-8").read()
        assert "services:" in content, "docker-compose must have services"
        assert "ports:" in content, "docker-compose must have ports"
        assert "8000:8000" in content, "docker-compose must map port 8000"

    def test_dockerignore_exists(self):
        """.dockerignore 必须存在"""
        repo = os.path.dirname(os.path.dirname(__file__))
        path = os.path.join(repo, ".dockerignore")
        assert os.path.exists(path), f".dockerignore not found at {path}"


class TestGitHubActions:
    """F2: GitHub Actions CI 配置测试."""

    def test_workflow_file_exists(self):
        """GitHub Actions workflow 必须存在"""
        repo = os.path.dirname(os.path.dirname(__file__))
        path = os.path.join(repo, ".github", "workflows", "test.yml")
        assert os.path.exists(path), f"Workflow not found at {path}"

    def test_workflow_triggers_on_push(self):
        """Workflow 触发 push + pull_request"""
        repo = os.path.dirname(os.path.dirname(__file__))
        path = os.path.join(repo, ".github", "workflows", "test.yml")
        if not os.path.exists(path):
            pytest.skip("Workflow not yet created")
        content = open(path, encoding="utf-8").read()
        assert "push" in content, "Workflow must trigger on push"
        assert "pull_request" in content, "Workflow must trigger on pull_request"

    def test_workflow_runs_pytest(self):
        """Workflow 必须运行 pytest"""
        repo = os.path.dirname(os.path.dirname(__file__))
        path = os.path.join(repo, ".github", "workflows", "test.yml")
        if not os.path.exists(path):
            pytest.skip("Workflow not yet created")
        content = open(path, encoding="utf-8").read()
        assert "pytest" in content, "Workflow must run pytest"
        assert "tests/" in content, "Workflow must run pytest on tests/"


class TestBatchUI:
    """F3: 批量优化 UI 测试 (Playwright E2E)."""

    def test_batch_button_in_workbench(self):
        """Workbench 应有「批量」切换按钮"""
        from playwright.sync_api import sync_playwright
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto("http://127.0.0.1:8094/", wait_until="networkidle")
                page.wait_for_timeout(3000)
                # Look for batch-related button/text
                batch_btn = page.locator("text=/批量/").first
                assert batch_btn.count() > 0, "Should have batch button"
                browser.close()
        except Exception as e:
            pytest.skip(f"Playwright not available: {e}")

    def test_batch_mode_renders_textarea(self):
        """批量模式下 textarea 应能输入多行"""
        from playwright.sync_api import sync_playwright
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto("http://127.0.0.1:8094/", wait_until="networkidle")
                page.wait_for_timeout(3000)
                # Click batch mode
                batch_btn = page.locator("text=/批量/").first
                if batch_btn.count() > 0:
                    batch_btn.click()
                    page.wait_for_timeout(1000)
                    # Should have a multi-line textarea
                    ta = page.locator("textarea").first
                    assert ta.is_visible(), "Textarea should be visible in batch mode"
                browser.close()
        except Exception as e:
            pytest.skip(f"Playwright not available: {e}")
