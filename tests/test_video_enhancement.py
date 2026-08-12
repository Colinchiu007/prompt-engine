"""视频提示词引擎增强测试（video-prompt-engine-enhancement）。

覆盖：
- 双级缓存：命中跳过 LLM、key 含语言、SQLite 跨实例持久、禁用开关、统计
- JSON 结构化输出重试：失败带提示重试、耗尽回退原文并标记
- 多平台专项策略：veo/kling/hailuo/doubao 注册 + 平台约束 + 语言段
- 输入分类：题材/镜头意图 + 维度建议 + system prompt 注入
- 多候选择优：evaluator 评分最优在前
- 评估与反馈闭环：evaluator 评分、feedback 沉淀/降级、空值校验
- 中文输出：output_language=zh
- API：/classify、/feedback、/cache/stats、platforms=已注册
- RAG 关键词兜底：向量无命中 → 平台种子命中
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from video_prompt_engine.models import VideoOptimizeRequest
from video_prompt_engine.optimizer import VideoOptimizer, JSON_RETRY_HINT
from video_prompt_engine.strategies import list_strategies, get_strategy
from video_prompt_engine.classifier import classify, suggest_dimensions
from video_prompt_engine.evaluator import evaluate, select_best
from video_prompt_engine.feedback import VideoFeedbackStore

VIDEO_LLM_JSON = (
    '{"prompt": "a sleek black cat dashes through a neon alley, cinematic medium-wide shot, slow dolly-in, '
    'cool blue and magenta palette, dramatic rim lighting", '
    '"shot": "medium_wide", "camera": "dolly", "motion_intensity": 7, '
    '"scene_transition": "cut", "continuity_token": "cat_neon_alley", "duration_hint": 5}'
)


def make_optimizer(cache_dir=None):
    return VideoOptimizer(cache_dir=cache_dir or tempfile.mkdtemp())


def mock_provider(value, *, error=None, side_effect=None):
    fake = Mock()
    fake.model_name = "mock-video"
    if side_effect is not None:
        fake.call.side_effect = side_effect
    elif error is not None:
        fake.call.side_effect = error
    else:
        fake.call.return_value = (value, 100)
    return fake


class TestCache:
    def test_cache_hit_skips_llm(self):
        o = make_optimizer()
        o._provider = mock_provider(VIDEO_LLM_JSON)
        req = VideoOptimizeRequest(prompt="a cat running", platform="generic_video")
        r1 = o.optimize(req)
        assert r1.cache_hit is False
        r2 = o.optimize(req)
        assert r2.cache_hit is True
        assert r2.optimized_prompt == r1.optimized_prompt
        assert o._provider.call.call_count == 1  # 第二次命中缓存不调 LLM

    def test_cache_key_includes_language(self):
        o = make_optimizer()
        o._provider = mock_provider(VIDEO_LLM_JSON)
        o.optimize(VideoOptimizeRequest(prompt="a cat", output_language="en"))
        o.optimize(VideoOptimizeRequest(prompt="a cat", output_language="zh"))
        assert o._provider.call.call_count == 2  # 语言不同 → 不同 key

    def test_cache_persists_across_instances(self):
        d = tempfile.mkdtemp()
        o1 = make_optimizer(d)
        o1._provider = mock_provider(VIDEO_LLM_JSON)
        o1.optimize(VideoOptimizeRequest(prompt="persist me", platform="generic_video"))
        o2 = make_optimizer(d)
        o2._provider = mock_provider(VIDEO_LLM_JSON)
        r = o2.optimize(VideoOptimizeRequest(prompt="persist me", platform="generic_video"))
        assert r.cache_hit is True
        assert o2._provider.call.call_count == 0

    def test_cache_disabled(self):
        cfg = {"optimizer": {"max_retries": 2}, "cache": {"enabled": False}, "knowledge": {"enabled": True}}
        o = VideoOptimizer(config=cfg, cache_dir=tempfile.mkdtemp())
        o._provider = mock_provider(VIDEO_LLM_JSON)
        o.optimize(VideoOptimizeRequest(prompt="a cat"))
        o.optimize(VideoOptimizeRequest(prompt="a cat"))
        assert o._provider.call.call_count == 2

    def test_cache_stats(self):
        o = make_optimizer()
        o._provider = mock_provider(VIDEO_LLM_JSON)
        o.optimize(VideoOptimizeRequest(prompt="a cat"))
        s = o.cache_stats()
        assert s["enabled"] is True
        assert s["memory_size"] >= 1 and s["sqlite_count"] >= 1


class TestJsonRetry:
    def test_invalid_json_retries_with_hint(self):
        o = make_optimizer()
        calls = {"n": 0}

        def side_effect(system_prompt, user_prompt, variant=0):
            calls["n"] += 1
            if calls["n"] == 1:
                return "I think the prompt should be: a cat. (not JSON)", 100
            return VIDEO_LLM_JSON, 100

        o._provider = mock_provider(None, side_effect=side_effect)
        r = o.optimize(VideoOptimizeRequest(prompt="a cat running"))
        assert "neon alley" in r.optimized_prompt
        assert r.retried == 1
        # 第二次调用必须携带"只输出严格 JSON"提示
        hint_call = o._provider.call.call_args_list[1]
        assert JSON_RETRY_HINT in hint_call.args[0]

    def test_retry_exhausted_falls_back_to_source(self):
        o = make_optimizer()
        o._provider = mock_provider("plain text not json at all, sorry")
        r = o.optimize(VideoOptimizeRequest(prompt="原文内容", platform="generic_video"))
        assert r.optimized_prompt == "原文内容"  # 回退原文
        assert r.retried == 2  # max_retries=2 次重试后耗尽


class TestPlatformStrategies:
    def test_registered(self):
        for p in ("veo", "kling", "hailuo", "doubao"):
            assert get_strategy(p) is not None, p

    def test_platform_notes(self):
        notes = {
            "veo": "long continuous takes",
            "kling": "motion physics",
            "hailuo": "rhythm",
            "doubao": "Chinese-language",
        }
        for p, note in notes.items():
            assert note in get_strategy(p).build_system_prompt(), p

    def test_language_routing_alignment_notes(self):
        """语言路由对齐：veo 英文优先 / doubao 中文优先 平台注记存在（与 Multi-Publish 路由一致）。"""
        assert "Veo is optimized for English prompts" in get_strategy("veo").build_system_prompt()
        assert "Prefer Chinese output" in get_strategy("doubao").build_system_prompt()

    def test_zh_language_section_all_strategies(self):
        for p in list_strategies():
            sp = get_strategy(p).build_system_prompt(output_language="zh")
            assert "## Output Language (MANDATORY)" in sp, p
            assert "中文" in sp, p
            sp_en = get_strategy(p).build_system_prompt(output_language="en")
            assert "English flowing prose" in sp_en, p


class TestClassification:
    def test_classify_history_and_scifi(self):
        info = classify("三国 关羽 古代 战场 万军中取敌将首级")
        assert "history" in info["genres"]
        info2 = classify("赛博朋克 霓虹 未来城市 追逐")
        assert "scifi" in info2["genres"]

    def test_suggest_dimensions(self):
        dims = suggest_dimensions("科幻 赛博 霓虹")
        assert "color" in dims and "scene" in dims

    def test_optimizer_injects_classification(self):
        o = make_optimizer()
        captured = {}

        def side_effect(system_prompt, user_prompt, variant=0):
            captured["sp"] = system_prompt
            return VIDEO_LLM_JSON, 100

        o._provider = mock_provider(None, side_effect=side_effect)
        o.optimize(VideoOptimizeRequest(prompt="三国 关羽 白马之战 万军中斩颜良"))
        assert "题材(genre)" in captured["sp"]
        assert "history" in captured["sp"]
class TestMultiCandidate:
    def test_best_candidate_first(self):
        o = make_optimizer()
        cand_short = '{"prompt": "cat", "shot": "", "camera": "", "motion_intensity": 1, "scene_transition": "", "continuity_token": "", "duration_hint": null}'

        def side_effect(system_prompt, user_prompt, variant=0):
            return (VIDEO_LLM_JSON if variant == 0 else cand_short), 100

        o._provider = mock_provider(None, side_effect=side_effect)
        r = o.optimize(VideoOptimizeRequest(prompt="a cat running in a neon city", num_candidates=2))
        assert len(r.candidates) == 2
        assert r.optimized_prompt == r.candidates[0]
        assert "neon alley" in r.candidates[0]  # 最优候选在前


class TestEvaluatorAndFeedback:
    def test_evaluate_score_range_and_length(self):
        long_prompt = (
            "A young warrior in black and gold armor rides a white horse through a vast ancient battlefield at dawn, "
            "dust rising from the ground, banners of the Han dynasty fluttering in the wind, soldiers marching behind, "
            "the environment is a misty mountain pass with burning campfires, the color palette is warm amber and deep "
            "blood red, the lighting is dramatic golden hour rim light with long shadows, the style is epic historical "
            "cinematic, wide establishing shot, slow dolly-in camera motion, motion intensity is high with charging "
            "cavalry and swirling flags, scene transition is a hard cut, this is a detailed and rich description of a "
            "historical war scene with full visual elements for an AI video generation model"
        )
        info = evaluate(
            long_prompt,
            {"shot": "wide", "camera": "dolly", "motion_intensity": 7},
            source_prompt="关羽白马之战 万军中斩颜良 三国历史",
            language="zh",
        )
        assert 0 <= info["score"] <= 100
        assert info["checks"]["length"] is True
        assert info["checks"]["elements_score"] > 0.5

    def test_select_best_picks_higher_score(self):
        good = (
            "a detailed cinematic prompt with subject, action, environment, lighting, color and style, wide shot camera dolly motion",
            {"shot": "wide", "camera": "dolly", "motion_intensity": 7},
        )
        bad = ("x", {})
        best = select_best([bad, good], source_prompt="a cat running", language="en")
        assert best[0] == good[0]

    def test_feedback_validation(self):
        store = VideoFeedbackStore(Path(tempfile.mkdtemp()) / "s.json")
        with pytest.raises(ValueError):
            store.submit("", "x", True)
        with pytest.raises(ValueError):
            store.submit("x", "", True)

    def test_feedback_good_appends_bad_downgrades(self):
        d = Path(tempfile.mkdtemp()) / "s.json"
        d.write_text(json.dumps([
            {"id": "seed-0001", "prompt_text": "旧种子", "quality_score": 5, "platform": "generic_video"}
        ], ensure_ascii=False), encoding="utf-8")
        store = VideoFeedbackStore(d)
        r = store.submit("原文", "优化后的详细提示词", True)
        assert r["status"] == "ok" and r["total"] == 2
        seeds = json.loads(d.read_text(encoding="utf-8"))
        assert seeds[-1]["quality_score"] == 9
        assert seeds[-1]["source"] == "user-feedback"
        # 坏评：源提示词质量分降级
        store.submit("优化后的详细提示词", "any", False)
        seeds = json.loads(d.read_text(encoding="utf-8"))
        assert seeds[-1]["quality_score"] == 8


class TestChineseOutput:
    def test_zh_language_flag(self):
        o = make_optimizer()
        o._provider = mock_provider(VIDEO_LLM_JSON)
        r = o.optimize(VideoOptimizeRequest(prompt="一只猫在霓虹城市奔跑", output_language="zh"))
        assert r.language == "zh"
        assert r.classification is not None

    def test_zh_system_prompt_has_chinese_instruction(self):
        o = make_optimizer()
        captured = {}

        def side_effect(system_prompt, user_prompt, variant=0):
            captured["sp"] = system_prompt
            return VIDEO_LLM_JSON, 100

        o._provider = mock_provider(None, side_effect=side_effect)
        o.optimize(VideoOptimizeRequest(prompt="三国历史", output_language="zh"))
        assert "中文" in captured["sp"]
        assert "Output Language" in captured["sp"]


class TestRagFallback:
    def test_keyword_fallback_returns_platform_seeds(self):
        from video_prompt_engine.rag_retriever import VideoRAGRetriever
        # 向量库目录不存在 → 仅种子关键词兜底路径
        cfg = {"knowledge": {"enabled": True, "persist_dir": str(Path(tempfile.mkdtemp()) / "no-index"), "retrieval": {"top_k": 3}}}
        rr = VideoRAGRetriever(cfg)
        assert rr._vector_store is None  # 向量库未构建 → 走关键词兜底
        items = rr.keyword_fallback("运镜 广告 分镜编排", "seedance")
        assert items
        assert all(i.get("platform") in ("seedance", "generic_video") for i in items)
        assert any("运镜" in str(i.get("document", "")) or "广告" in str(i.get("document", "")) for i in items)

    def test_retrieve_few_shot_falls_back_to_keywords(self):
        from video_prompt_engine.rag_retriever import VideoRAGRetriever
        cfg = {"knowledge": {"enabled": True, "persist_dir": str(Path(tempfile.mkdtemp()) / "no-index"), "retrieval": {"top_k": 3}}}
        rr = VideoRAGRetriever(cfg)
        req = VideoOptimizeRequest(prompt="运镜 广告 分镜编排", platform="seedance")
        section = rr.retrieve_few_shot(req, platform="seedance")
        assert "高质量视频参考示例" in section


class TestApiEnhancements:
    def _client(self):
        from video_prompt_engine.api import rest
        o = make_optimizer()
        o._provider = mock_provider(VIDEO_LLM_JSON)
        rest._optimizer = o
        return TestClient(rest.app)

    def test_platforms_returns_registered(self):
        client = self._client()
        r = client.get("/v1/video/platforms")
        assert r.status_code == 200
        assert {"veo", "kling", "hailuo", "doubao", "seedance", "generic_video"} <= set(r.json()["platforms"])

    def test_classify_endpoint(self):
        client = self._client()
        r = client.post("/v1/video/classify", json={"prompt": "三国 关羽 古代战场"})
        assert r.status_code == 200
        assert "history" in r.json()["genres"]

    def test_feedback_endpoint(self):
        from video_prompt_engine.api import rest
        tmp_seed = Path(tempfile.mkdtemp()) / "seed.json"

        class FakeStore(VideoFeedbackStore):
            def __init__(self, *a, **k):
                super().__init__(tmp_seed)

        with patch("video_prompt_engine.feedback.VideoFeedbackStore", FakeStore):
            client = self._client()
            r = client.post("/v1/video/feedback", json={"prompt_text": "原文", "result_prompt": "结果", "good": True})
            assert r.status_code == 200
            assert r.json()["status"] == "ok"
            r2 = client.post("/v1/video/feedback", json={"prompt_text": "", "result_prompt": "", "good": False})
            assert r2.status_code == 422

    def test_cache_stats_endpoint(self):
        client = self._client()
        r = client.get("/v1/video/cache/stats")
        assert r.status_code == 200
        assert r.json()["enabled"] is True

    def test_optimize_zh_through_api(self):
        from video_prompt_engine.api import rest
        o = make_optimizer()
        o._provider = mock_provider(VIDEO_LLM_JSON)
        rest._optimizer = o
        client = TestClient(rest.app)
        r = client.post("/v1/video/optimize", json={"prompt": "三国 关羽 白马之战", "output_language": "zh", "platform": "generic_video"})
        assert r.status_code == 200
        body = r.json()
        assert body["language"] == "zh"
        assert body["optimized_prompt"]

class TestReviewFixes:
    """外部审查（claude targeted review）修复回归。"""

    def test_cache_key_includes_style(self):
        """Critical: 缓存 key 必须包含 style（style 改变 system prompt → 输出）。"""
        o = make_optimizer()
        o._provider = mock_provider(VIDEO_LLM_JSON)
        o.optimize(VideoOptimizeRequest(prompt="a cat", style="cinematic", platform="generic_video"))
        o.optimize(VideoOptimizeRequest(prompt="a cat", style="realistic", platform="generic_video"))
        assert o._provider.call.call_count == 2  # style 不同 → 不同 key

    def test_cache_key_no_pipe_collision(self):
        """Warning: 组件哈希后，含 | 的 prompt/negative 不再碰撞。"""
        o = make_optimizer()
        o._provider = mock_provider(VIDEO_LLM_JSON)
        # (prompt="a|b", neg="c") 与 (prompt="a", neg="b|c") 必须不同 key
        o.optimize(VideoOptimizeRequest(prompt="a|b", negative_prompt="c", platform="generic_video"))
        o.optimize(VideoOptimizeRequest(prompt="a", negative_prompt="b|c", platform="generic_video"))
        assert o._provider.call.call_count == 2

    def test_sensitive_context_in_list_rejected(self):
        """Warning: 敏感键递归进 list 元素。"""
        from video_prompt_engine.models import assert_no_sensitive_context
        with pytest.raises(ValueError, match="敏感"):
            assert_no_sensitive_context({"character_list": [{"name": "关羽", "api_key": "sk-xxx"}]})
        with pytest.raises(ValueError, match="敏感"):
            assert_no_sensitive_context({"nested": [{"a": [{"token": "t"}]}]})

    def test_classifier_single_char_no_false_positive(self):
        """Info: 去掉单字「战」后，「战斗动作」不再误判为历史题材。"""
        info = classify("激烈的战斗动作场面，武术对决")
        assert "history" not in info["genres"]
        assert classify("三国 古代 战争 战场")["genres"] == ["history"]

    def test_feedback_writes_writable_dir_not_package(self):
        """Warning: feedback 落可写目录（非包内种子文件）。"""
        from video_prompt_engine.api import rest
        o = make_optimizer()
        rest._optimizer = o
        # 用临时目录作为 cache.dir
        o.config.setdefault("cache", {})["dir"] = tempfile.mkdtemp()
        client = TestClient(rest.app)
        r = client.post("/v1/video/feedback", json={"prompt_text": "原文", "result_prompt": "结果", "good": True})
        assert r.status_code == 200
        fb = Path(o.config["cache"]["dir"]) / "feedback_seed.json"
        assert fb.exists()
