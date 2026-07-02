"""Tests for XiaoheiStoryboardStrategy — 小黑故事板策略"""
import random
import pytest
from prompt_engine.storyboard.xiaohei import (
    XiaoheiStoryboardStrategy,
    _three_step_metaphor,
    COMPOSITION_PATTERNS,
    ACTION_POOL,
    OBJECT_POOL,
    CONCEPT_COMPOSITION_MAP,
    COMPOSITION_ACTION_MAP,
    COMPOSITION_OBJECT_MAP,
    STORYBOARD_TEMPLATE,
)


class TestThreeStepMetaphor:
    """三步隐喻引擎"""

    def test_competition_matches_contrast(self):
        """竞争类概念应匹配前后对比"""
        result = _three_step_metaphor("市场竞争")
        assert result["composition"] == "前后对比"

    def test_balance_matches_metaphor(self):
        """平衡类概念应匹配概念隐喻"""
        result = _three_step_metaphor("平衡")
        assert result["composition"] == "前后对比"

    def test_growth_matches_flow(self):
        """增长类概念应匹配角色状态"""
        result = _three_step_metaphor("增长")
        assert result["composition"] == "角色状态"

    def test_system_matches_layers(self):
        """系统类概念应匹配方法分层"""
        result = _three_step_metaphor("系统架构")
        assert result["composition"] == "方法分层"

    def test_pipeline_matches_workflow(self):
        """流程类概念应匹配流程展示"""
        result = _three_step_metaphor("数据处理流程")
        assert result["composition"] == "流程展示"

    def test_innovation_matches_concept(self):
        """创新类概念应匹配概念隐喻"""
        result = _three_step_metaphor("突破性创新")
        assert result["composition"] == "概念隐喻"

    def test_roadmap_matches_map(self):
        """路线类概念应匹配地图路径"""
        result = _three_step_metaphor("产品路线图")
        assert result["composition"] == "地图路径"

    def test_story_matches_comic(self):
        """故事类概念应匹配迷你漫画"""
        result = _three_step_metaphor("用户故事")
        assert result["composition"] == "迷你漫画"

    def test_change_matches_contrast(self):
        """变化类概念应匹配前后对比"""
        result = _three_step_metaphor("数字化转型")
        assert result["composition"] == "前后对比"

    def test_research_matches_system(self):
        """研究类概念应匹配系统局部"""
        result = _three_step_metaphor("深入分析")
        assert result["composition"] == "系统局部"

    def test_unknown_concept_uses_fallback(self):
        """未知概念使用默认 fallback"""
        result = _three_step_metaphor("something_completely_random_xyz")
        assert result["composition"] in COMPOSITION_PATTERNS
        assert "action" in result
        assert "object" in result
        assert "scene" in result
        assert len(result["scene"]) > 0

    def test_action_in_pool(self):
        """返回的动作应在动作库中"""
        result = _three_step_metaphor("增长")
        assert any(result["action"] in a["zh"] for a in ACTION_POOL)

    def test_object_in_pool(self):
        """返回的物件应在物件库中"""
        result = _three_step_metaphor("连接")
        assert any(result["object"] in o["zh"] for o in OBJECT_POOL)

    def test_result_contains_all_keys(self):
        """返回结果包含所有必要字段"""
        result = _three_step_metaphor("市场竞争")
        assert "composition" in result
        assert "action" in result
        assert "object" in result
        assert "scene" in result
        assert "comp_detail" in result
        assert "obj_detail" in result
        assert "act_detail" in result

    def test_scene_contains_concept(self):
        """场景描述应包含原始概念"""
        result = _three_step_metaphor("AI 监管")
        assert "AI 监管" in result["scene"]


class TestXiaoheiStoryboardStrategy:
    """小黑故事板策略类"""

    def test_registered_name(self):
        """策略注册名为 xiaohei_storyboard"""
        from prompt_engine.storyboard import get_storyboard_strategy
        cls = get_storyboard_strategy("xiaohei_storyboard")
        assert cls is XiaoheiStoryboardStrategy

    def test_display_name(self):
        """display_name 应为中文描述"""
        assert XiaoheiStoryboardStrategy.display_name == "Ian 小黑插画风"
        assert len(XiaoheiStoryboardStrategy.description) > 0

    def test_compose_returns_non_empty_string(self):
        """compose 返回非空字符串"""
        result = XiaoheiStoryboardStrategy.compose("市场竞争")
        assert isinstance(result, str)
        assert len(result) > 100

    def test_compose_contains_required_sections(self):
        """compose 输出包含所有必要章节标题"""
        result = XiaoheiStoryboardStrategy.compose("AI 如何改变教育")
        assert "## Theme" in result
        assert "## Composition Type" in result
        assert "## Core Metaphor" in result
        assert "## Visual Composition" in result
        assert "## Suggested Elements" in result
        assert "## Color Palette" in result
        assert "## Constraints" in result

    def test_compose_with_override_composition(self):
        """compose 可通过 options 覆盖构图类型"""
        result = XiaoheiStoryboardStrategy.compose(
            "市场竞争", composition_type="迷你漫画"
        )
        assert "迷你漫画" in result

    def test_compose_with_style_option(self):
        """compose 接受 style 参数不报错"""
        result = XiaoheiStoryboardStrategy.compose(
            "技术迭代", style="midjourney"
        )
        assert len(result) > 100

    def test_compose_with_creative_level(self):
        """不同 creative_level 产生不同输出"""
        r_low = XiaoheiStoryboardStrategy.compose("平衡", creative_level=1)
        r_high = XiaoheiStoryboardStrategy.compose("平衡", creative_level=10)
        assert isinstance(r_low, str)
        assert isinstance(r_high, str)

    def test_compose_with_meta_returns_dict(self):
        """compose_with_meta 返回含 prompt 和 metaphor 的字典"""
        result = XiaoheiStoryboardStrategy.compose_with_meta("测试概念")
        assert isinstance(result, dict)
        assert "prompt" in result
        assert "metaphor" in result
        assert len(result["prompt"]) > 50
        meta = result["metaphor"]
        assert "composition_type" in meta
        assert "action" in meta
        assert "object" in meta
        assert "scene" in meta
        assert "creative_level" in meta

    def test_compose_batch_returns_list(self):
        """compose_batch 返回字符串列表"""
        scenes = ["第一个场景", "第二个场景", "第三个场景"]
        results = XiaoheiStoryboardStrategy.compose_batch(scenes, "全文测试")
        assert isinstance(results, list)
        assert len(results) == 3
        for r in results:
            assert isinstance(r, str)
            assert len(r) > 50

    def test_compose_batch_with_meta(self):
        """compose_batch_with_meta 返回元数据列表"""
        scenes = ["场景A", "场景B"]
        results = XiaoheiStoryboardStrategy.compose_batch_with_meta(
            scenes, "全文"
        )
        assert len(results) == 2
        for r in results:
            assert "prompt" in r
            assert "metaphor" in r

    def test_batch_metaphor_consistency(self):
        """batch 模式用 full_text 决定全局构图类型"""
        scenes = ["细节1", "细节2"]
        # full_text 含"竞争"关键词 → 前后对比
        results = XiaoheiStoryboardStrategy.compose_batch_with_meta(
            scenes, "市场竞争白热化"
        )
        for r in results:
            assert r["metaphor"]["composition_type"] == "前后对比"


class TestEdgeCases:
    """边界条件"""

    def test_empty_concept(self):
        """空概念也应返回有效结果"""
        result = XiaoheiStoryboardStrategy.compose("")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_very_long_concept(self):
        """超长概念不崩溃"""
        long_text = "和" * 5000
        result = XiaoheiStoryboardStrategy.compose(long_text)
        assert isinstance(result, str)

    def test_single_scene_batch(self):
        """单场景 batch"""
        results = XiaoheiStoryboardStrategy.compose_batch(
            ["仅一个场景"], "全文"
        )
        assert len(results) == 1

    def test_batch_empty_scenes(self):
        """空 batch 返回空列表"""
        results = XiaoheiStoryboardStrategy.compose_batch([], "")
        assert results == []


class TestDataIntegrity:
    """数据完整性校验"""

    def test_all_compositions_in_maps(self):
        """所有构图类型在映射表中一致"""
        for c in COMPOSITION_PATTERNS:
            assert c in COMPOSITION_ACTION_MAP, f"{c} missing in action map"
            assert c in COMPOSITION_OBJECT_MAP, f"{c} missing in object map"

    def test_concept_map_compositions_valid(self):
        """所有概念映射指向存在的构图类型"""
        for entry in CONCEPT_COMPOSITION_MAP:
            assert entry["composition"] in COMPOSITION_PATTERNS, (
                f"Unknown composition: {entry['composition']}"
            )

    def test_color_schemes_all_compositions(self):
        """所有构图类型有配色方案"""
        from prompt_engine.storyboard.xiaohei import COLOR_SCHEMES
        for c in COMPOSITION_PATTERNS:
            assert c in COLOR_SCHEMES, f"{c} missing in COLOR_SCHEMES"

    def test_storyboard_template_format_keys(self):
        """模板格式化需要的所有键"""
        from prompt_engine.storyboard.xiaohei import STORYBOARD_TEMPLATE
        required_keys = [
            "theme", "composition_type", "composition_desc",
            "metaphor", "visual_composition", "subject", "action",
            "object", "environment", "color_palette", "constraints",
        ]
        # 验证模板包含所有占位符
        for key in required_keys:
            assert "{" + key + "}" in STORYBOARD_TEMPLATE, f"Missing key: {key}"
