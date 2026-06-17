"""Prompt-as-Code 模板系统测试"""
import pytest


class TestPromptBlock:
    """测试原子化 prompt 块."""

    def test_import_prompt_block(self):
        from prompt_engine.template_engine import PromptBlock
        pb = PromptBlock(name="subject", template="A {adjective} {subject}")
        assert pb.name == "subject"
        assert pb.template == "A {adjective} {subject}"

    def test_render_basic(self):
        from prompt_engine.template_engine import PromptBlock
        pb = PromptBlock(name="subject", template="A {adjective} {subject}")
        result = pb.render(adjective="majestic", subject="cat")
        assert result == "A majestic cat"

    def test_render_with_params_pool(self):
        from prompt_engine.template_engine import PromptBlock
        pb = PromptBlock(
            name="subject",
            template="A {adjective} {subject} {action}",
            params={
                "adjective": ["majestic", "serene", "vibrant"],
                "subject": ["cat", "mountain", "city"],
                "action": ["running", "standing", "floating"],
            },
        )
        # 用 params 池中的随机值渲染
        result = pb.render_with_params()
        assert result.startswith("A ")
        assert any(adj in result for adj in ["majestic", "serene", "vibrant"])
        assert any(subj in result for subj in ["cat", "mountain", "city"])

    def test_render_with_override(self):
        from prompt_engine.template_engine import PromptBlock
        pb = PromptBlock(
            name="subject",
            template="A {adjective} {subject}",
            params={"adjective": ["majestic"], "subject": ["cat"]},
        )
        # override 参数优先
        result = pb.render_with_params(adjective="tiny")
        assert "tiny" in result
        assert "cat" in result

    def test_block_str_representation(self):
        from prompt_engine.template_engine import PromptBlock
        pb = PromptBlock(name="lighting", template="Soft {light_type} lighting")
        assert "lighting" in str(pb)


class TestPromptTemplate:
    """测试组合模板."""

    def test_import_prompt_template(self):
        from prompt_engine.template_engine import PromptTemplate, PromptBlock
        template = PromptTemplate(
            name="test",
            blocks=[
                PromptBlock(name="subject", template="A {adjective} {subject}"),
                PromptBlock(name="lighting", template="{light_type} lighting"),
            ],
        )
        assert template.name == "test"
        assert len(template.blocks) == 2

    def test_render_template(self):
        from prompt_engine.template_engine import PromptTemplate, PromptBlock
        template = PromptTemplate(
            name="portrait",
            blocks=[
                PromptBlock(name="subject", template="A {adjective} {subject}"),
                PromptBlock(name="lighting", template="{light_type} lighting"),
            ],
            separator=", ",
        )
        result = template.render(adjective="beautiful", subject="woman", light_type="soft")
        assert "beautiful woman" in result
        assert "soft lighting" in result

    def test_render_low_creative(self):
        """低创意等级用简单参数."""
        from prompt_engine.template_engine import PromptTemplate, PromptBlock
        template = PromptTemplate(
            name="portrait",
            blocks=[
                PromptBlock(
                    name="subject",
                    template="A {adjective} {subject}",
                    params={"adjective": ["beautiful", "stunning"], "subject": ["woman", "man"]},
                ),
                PromptBlock(
                    name="lighting",
                    template="{light_type} lighting",
                    params={"light_type": ["soft", "dramatic"]},
                ),
            ],
            separator=", ",
        )
        result = template.render(creative_level=2)
        # 低创意：blocks 全渲染，简单参数
        assert len(result) > 10
        assert "lighting" in result

    def test_render_with_style_category(self):
        from prompt_engine.template_engine import PromptTemplate, PromptBlock
        from prompt_engine.models import StyleCategory
        template = PromptTemplate(
            name="portrait",
            style_categories=[StyleCategory.LIGHTING],
            blocks=[
                PromptBlock(name="subject", template="{subject}"),
                PromptBlock(name="lighting", template="{light_type} lighting"),
            ],
            separator=", ",
        )
        assert StyleCategory.LIGHTING in template.style_categories


class TestIntegrationWithOptimizer:
    """测试模板引擎与 optimizer 的集成."""

    def test_template_supports_creative_level_scale(self):
        from prompt_engine.template_engine import PromptTemplate, PromptBlock
        template = PromptTemplate(
            name="generic",
            blocks=[
                PromptBlock(name="subject", template="{subject}"),
                PromptBlock(name="lighting", template="{light_type} lighting"),
            ],
            separator=", ",
        )
        for level in [1, 5, 10]:
            result = template.render(subject="cat", light_type="soft", creative_level=level)
            assert "cat" in result
            assert "lighting" in result
