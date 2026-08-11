"""Web 前端模板契约测试（静态断言，无浏览器依赖）

背景（bug-reflection 2026-08-11）：in-DOM 模板中 <CompareTab />（PascalCase 自闭合）被
浏览器小写化为 <comparetab>，Vue 解析链仅尝试 camelize+capitalize（'Comparetab'），
匹配不到注册名 'CompareTab' → 组件未解析、页签空白（生产版 Vue 静默无警告）。
另：window.__PE 曾引用 Workbench 组件内的局部函数 copyText → ReferenceError 整页空白。

本测试以静态断言拦截同类回归：
1. 新增页签组件标签必须用 kebab-case（compare-tab），禁止 PascalCase 自闭合标签；
2. window.__PE 只暴露全局可访问对象（api），禁止引用组件内局部函数；
3. compare-tab.js 必须被引用且组件已注册。
"""
from pathlib import Path

WEB_DIR = Path(__file__).resolve().parent.parent / "prompt_engine" / "web"
INDEX = WEB_DIR / "index.html"


def _read(name: str) -> str:
    return (WEB_DIR / name).read_text(encoding="utf-8")


class TestWebTemplateContract:
    def test_compare_tab_uses_kebab_case_tag(self):
        """对比验证组件标签必须用 kebab-case（in-DOM 模板大小写陷阱）。"""
        html = _read("index.html")
        assert "<compare-tab>" in html, "缺少 kebab-case 标签 <compare-tab>"
        # 禁止 PascalCase 自闭合组件标签（会被浏览器小写化后无法还原注册名）
        assert "<CompareTab" not in html, "禁止使用 PascalCase 组件标签 <CompareTab>"

    def test_shared_pe_only_exposes_global_api(self):
        """window.__PE 只暴露全局可访问对象，不得引用组件内局部函数。"""
        html = _read("index.html")
        # copyText/isEnglish 是 Workbench setup() 内局部函数，不能出现在 __PE 中
        seg = html.split("window.__PE =")[1].split("\n")[0]
        assert "copyText" not in seg, "window.__PE 不能引用组件内局部函数 copyText"
        assert "isEnglish" not in seg, "window.__PE 不能引用组件内局部函数 isEnglish"
        assert "api" in seg, "window.__PE 应暴露 api 助手"

    def test_compare_tab_js_loaded_and_registered(self):
        """compare-tab.js 被引用，且组件注册名与 kebab 标签匹配。"""
        html = _read("index.html")
        assert 'src="compare-tab.js"' in html, "index.html 必须加载 compare-tab.js"
        assert "CompareTab: window.CompareTab" in html, "必须注册 CompareTab 组件"
        # 注册名与标签解析链必须匹配：kebab 'compare-tab' → camelize 'compareTab' → capitalize 'CompareTab'
        js = _read("compare-tab.js")
        assert "window.CompareTab = CompareTab" in js, "compare-tab.js 必须导出 window.CompareTab"
        assert "name: 'CompareTab'" in js, "组件 name 应为 CompareTab"