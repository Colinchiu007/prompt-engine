"""DSL 模板语法解析器测试 — 借鉴 sd-dynamic-prompts."""
import pytest


class TestVariantSyntax:
    """测试 {option1|option2} 变体语法."""

    def test_parse_variant(self):
        from prompt_engine.dsl_parser import parse
        result = parse("A {cat|dog} sitting")
        assert result is not None

    def test_render_variant(self):
        from prompt_engine.dsl_parser import parse, render
        result = render("A {cat|dog} sitting")
        assert "cat" in result or "dog" in result
        assert result.startswith("A ")
        assert "sitting" in result

    def test_variant_all_options_appear(self):
        from prompt_engine.dsl_parser import render
        results = set()
        for _ in range(50):
            results.add(render("color is {red|green|blue}"))
        assert len(results) > 1  # 至少两种结果
        assert "color is red" in results
        assert "color is green" in results
        assert "color is blue" in results

    def test_multiple_variants(self):
        from prompt_engine.dsl_parser import render
        result = render("A {big|small} {cat|dog}")
        parts = result.split()
        assert parts[1] in ("big", "small")
        assert parts[2] in ("cat", "dog")


class TestWildcardSyntax:
    """测试 __wildcard__ 通配符语法."""

    def test_parse_wildcard(self):
        from prompt_engine.dsl_parser import parse
        result = parse("__colors__ __animals__")
        assert result is not None

    def test_wildcard_with_default_pool(self):
        from prompt_engine.dsl_parser import render, register_wildcard_pool
        register_wildcard_pool("colors", ["red", "green", "blue"])
        result = render("color is __colors__")
        assert result.startswith("color is ")
        assert result.split()[-1] in ("red", "green", "blue")

    def test_wildcard_no_pool_returns_placeholder(self):
        from prompt_engine.dsl_parser import render
        # 未注册的通配符返回原样
        result = render("__unknown__")
        assert "__unknown__" in result


class TestQuantitySyntax:
    """测试 N$$ 数量限定语法."""

    def test_quantity_basic(self):
        from prompt_engine.dsl_parser import render
        result = render("{2$$artist1|artist2|artist3}")
        # 应包含恰好 2 个 artist
        parts = result.split(", ")
        assert 1 <= len(parts) <= 3  # 随机 2 个，可能 2

    def test_quantity_single(self):
        from prompt_engine.dsl_parser import render
        result = render("{1$$a|b|c}")
        assert result in ("a", "b", "c")


class TestEscapeSyntax:
    """测试转义语法."""

    def test_escape_brace(self):
        from prompt_engine.dsl_parser import render
        result = render("This is \\{not a variant\\}")
        assert "{not a variant}" in result


class TestNestedSyntax:
    """测试嵌套语法."""

    def test_nested_variant(self):
        from prompt_engine.dsl_parser import render
        result = render("{__color__|{red|blue}}")
        assert len(result) > 0


class TestIntegration:
    """测试与 PromptTemplate 的集成."""

    def test_dsl_in_prompt_block(self):
        from prompt_engine.template_engine import PromptBlock
        from prompt_engine.dsl_parser import render
        # PromptBlock 可以渲染 DSL 模板
        block = PromptBlock(name="subject", template="A {big|small} {cat|dog}")
        # 这里直接渲染 DSL（非传统 format）
        result = render(block.template)
        assert any(word in result for word in ["big", "small"])
        assert any(word in result for word in ["cat", "dog"])
