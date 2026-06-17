"""
前端 Web 看板 E2E 测试 — Playwright
启动要求：uvicorn 跑在 8090
"""
import os
import pytest

SERVER_URL = os.environ.get("TEST_SERVER_URL", "http://127.0.0.1:8094")


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        yield browser
        browser.close()


@pytest.fixture(scope="module")
def page(browser):
    page = browser.new_page()
    page.goto(SERVER_URL, wait_until="networkidle", timeout=15000)
    yield page
    page.close()


class TestWebE2E:
    """前端 Web 看板 E2E 测试."""

    def test_no_console_errors(self, page):
        """页面无 JS 错误"""
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.reload(wait_until="networkidle", timeout=10000)
        assert not errors, f"Page errors: {errors}"

    def test_workbench_mounts(self, page):
        """Workbench 组件 mount 后可见"""
        el_count = page.evaluate("document.querySelectorAll('.el-card').length")
        # Check the debug div is visible
        debug = page.locator("#debug-tab")
        if debug.count() > 0:
            print(f"DEBUG TAB: {debug.first.inner_text()}")
        buttons = page.locator("button:has-text('优化 Prompt')")
        assert buttons.count() >= 1, f"Workbench 优化按钮未渲染. el-card={el_count}"
        textarea = page.locator("textarea").first
        assert textarea.is_visible(), "textarea 不可见"

    def test_diagnose_dashboard(self, page):
        """诊断 Dashboard 为何不渲染"""
        msgs = []
        errs = []
        page.on("console", lambda m: msgs.append((m.type, m.text)))
        page.on("pageerror", lambda e: errs.append(str(e)))
        page.reload(wait_until="networkidle")
        page.wait_for_timeout(2000)
        page.click("text=数据看板")
        page.wait_for_timeout(3000)
        el_count = page.evaluate("document.querySelectorAll('.el-card').length")
        main_html_len = page.evaluate("document.querySelector('el-main')?.innerHTML?.length || 0")
        echarts_loaded = page.evaluate("typeof window.echarts")
        vue_errors = page.evaluate("window.__vue_error || []")
        # Try to find the Vue app instance
        vue_app = page.evaluate("""(() => {
            const app = document.getElementById('app');
            return {
                hasApp: !!app,
                hasVueApp: !!(app && app.__vue_app__),
                appKeys: app ? Object.keys(app).slice(0, 5) : [],
                bodyChildren: document.body.children.length,
                sectionCount: document.querySelectorAll('section').length
            };
        })()""")
        print(f"\nVue state: {vue_app}")
        # Also try to walk the DOM to find Dashboard
        dash_in_dom = page.evaluate("""(() => {
            const el = document.querySelector('[data-v-app]') || document.getElementById('app');
            if (!el) return 'no root';
            // Find all components in DOM
            const allDivs = el.querySelectorAll('div');
            return {
                divCount: allDivs.length,
                hasStatCard: !!document.querySelector('.el-card')
            };
        })()""")
        print(f"DOM walk: {dash_in_dom}")
        for kind, text in msgs[-30:]:
            print(f"  [console.{kind}] {text}")
        for e in vue_errors:
            print(f"  [VUE ERROR] {e}")
        for e in errs:
            print(f"  [pageerror] {e}")
        print(f"\nECharts loaded: {echarts_loaded}")
        print(f"el-main content: {main_html_len}b, el-card: {el_count}")
        html = page.content()
        with open("C:/Users/邱领/AppData/Local/Temp/dash_after.html", "w", encoding="utf-8") as f:
            f.write(html)
        assert el_count > 0, f"Dashboard has 0 cards. Errors: {errs}, console: {msgs[-5:]}"

    def test_click_settings_renders(self, page):
        """点击配置后渲染"""
        page.click("text=配置")
        page.wait_for_timeout(2000)
        assert page.locator(".el-card").count() > 0, "Settings 0 cards"

    def test_workbench_platforms_loaded(self, page):
        """Workbench 平台下拉框值匹配后端"""
        page.click("text=Prompt 工作台")
        page.wait_for_timeout(1000)
        page.locator(".el-select").first.click()
        page.wait_for_timeout(500)
        # Should see options
        options = page.locator(".el-select-dropdown__item")
        assert options.count() >= 7, f"Only {options.count()} options"
