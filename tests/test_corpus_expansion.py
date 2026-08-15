"""video-corpus-expansion 回归测试（组2-5）：
语料目录门禁 / loader 语义标注 / few-shot 负样本排除 / evaluate_negatives 校验模式。
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import build_corpus_index
from video_prompt_engine.evaluator import evaluate_negatives
from video_prompt_engine.knowledge.loader import load_seed_video_prompts
from video_prompt_engine.rag_retriever import VideoRAGRetriever

ROOT = Path(__file__).resolve().parent.parent
FAILURE_SAMPLES = json.loads(
    (ROOT / "video_prompt_engine/knowledge/seed_failure_samples.json").read_text(encoding="utf-8")
)


def _good_entry(eid="c-001", text=None, **overrides):
    item = {
        "id": eid,
        "title": "t",
        "description": "d",
        "prompt_text": text or ("A cinematic tracking shot through the neon city at dusk. " * 6),
        "language": "en",
        "platform": "generic_video",
        "tier": "refined",
        "quality_score": 8,
        "source": "test",
    }
    item.update(overrides)
    return item


class TestCorpusIndexBuild:
    def test_merge_dedupe_and_validate(self, tmp_path):
        d1 = tmp_path / "a"
        d2 = tmp_path / "b"
        d1.mkdir()
        d2.mkdir()
        shared_text = "A slow-motion tracking shot with lens flare through the fog. " * 5
        (d1 / "f1.json").write_text(
            json.dumps([_good_entry("c-001", shared_text), _good_entry("c-002")]), encoding="utf-8"
        )
        # 重复 prompt_text（保留首条）+ 非法条目（缺 tier）
        (d2 / "f2.json").write_text(
            json.dumps([_good_entry("c-003", shared_text), _good_entry("c-004", tier="")]),
            encoding="utf-8",
        )
        out = tmp_path / "index.json"
        rc = build_corpus_index.build([d1, d2], out, strict=False)
        assert rc == 0
        merged = json.loads(out.read_text(encoding="utf-8"))
        assert len(merged) == 2                       # 去重 1 条 + 跳过 1 条非法
        assert merged[0]["id"] == "c-001"             # 首条保留
        assert [e["id"] for e in merged] == ["c-001", "c-002"]

    def test_strict_fail_closed(self, tmp_path):
        d = tmp_path / "bad"
        d.mkdir()
        (d / "f.json").write_text(
            json.dumps([_good_entry("c-005", tier="unknown_tier")]), encoding="utf-8"
        )
        out = tmp_path / "index.json"
        assert build_corpus_index.build([d], out, strict=True) == 1
        assert not out.exists()                       # fail-closed：不产出

    def test_normalize_defaults(self, tmp_path):
        d = tmp_path / "norm"
        d.mkdir()
        # 缺失新字段 → 按 positive + few-shot 归一（组3.1）；显式非法值 → 门禁跳过（组2.2）
        (d / "f.json").write_text(
            json.dumps([_good_entry("c-006", corpus_type="evil", applicable_to="nope"),
                        _good_entry("c-008")]),
            encoding="utf-8",
        )
        out = tmp_path / "index.json"
        build_corpus_index.build([d], out, strict=False)
        merged = json.loads(out.read_text(encoding="utf-8"))
        assert [e["id"] for e in merged] == ["c-008"]     # 非法值条目被跳过
        assert merged[0]["corpus_type"] == "positive"     # 缺失 → 归一
        assert merged[0]["applicable_to"] == "few-shot"

    def test_short_prompt_rejected(self, tmp_path):
        d = tmp_path / "short"
        d.mkdir()
        (d / "f.json").write_text(
            json.dumps([_good_entry("c-007", text="too short")]), encoding="utf-8"
        )
        out = tmp_path / "index.json"
        build_corpus_index.build([d], out, strict=False)
        assert json.loads(out.read_text(encoding="utf-8")) == []


class TestLoaderSemantics:
    def _load_all(self):
        # 生产调用形态：主文件 + higgsfield 原文件 + 语料索引 + 负样本资产（显式 extra 列表）
        kb = ROOT / "video_prompt_engine/knowledge"
        return load_seed_video_prompts(
            kb / "seed_video_prompts.json",
            [
                kb / "seed_higgsfield_prompts.json",
                kb / "corpus_index.json",
                kb / "seed_failure_samples.json",
            ],
        )

    def test_negative_entries_auto_merged(self):
        entries = self._load_all()
        neg = [e for e in entries if e.corpus_type == "negative"]
        assert len(neg) == len(FAILURE_SAMPLES)
        assert all(e.applicable_to == "eval" for e in neg)
        assert all(e.failure_tags for e in neg)
        sample = next(e for e in neg if e.id == "fail-001")
        assert sample.failure_tags == ["exposure_break"]
        assert sample.tier == "refined"

    def test_old_entries_zero_regression(self):
        entries = self._load_all()
        old = [e for e in entries if e.id.startswith(("seed-", "awv-", "hg-scene"))]
        assert old
        assert all(
            e.corpus_type == "positive" and e.applicable_to == "few-shot"
            and not e.failure_tags and not e.meta and not e.tier
            for e in old
        )

    def test_corpus_index_merged_with_tier(self):
        entries = self._load_all()
        demo = [e for e in entries if e.id.startswith("hg-demo")]
        assert len(demo) == 2
        assert {e.tier for e in demo} == {"refined", "batch"}

    def test_single_path_extra_backward_compat(self, tmp_path):
        main = tmp_path / "main.json"
        extra = tmp_path / "extra.json"
        main.write_text(json.dumps([{"id": "m1", "prompt_text": "A quiet wide shot. " * 6}]), encoding="utf-8")
        extra.write_text(json.dumps([{"id": "x1", "prompt_text": "A neon rain chase. " * 6}]), encoding="utf-8")
        entries = load_seed_video_prompts(main, extra)   # 单 extra 路径向后兼容
        assert [e.id for e in entries] == ["m1", "x1"]
        assert entries[1].corpus_type == "positive"      # 旧格式按正样本归一


class TestRAGFewShotFilter:
    def _retriever_with_entries(self, entries):
        r = VideoRAGRetriever.__new__(VideoRAGRetriever)
        r._config = {"knowledge": {"enabled": True}}
        r._seed_entries = entries
        r._vector_store = None
        return r

    def _mk(self, cid, ctype, applicable="few-shot", text=None):
        return {
            "id": cid, "title": cid, "description": "", "document": text or ("A neon city chase. " * 6),
            "language": "en", "platform": "generic_video", "style": "",
            "categories": [], "quality_score": 8, "source": "test",
            "corpus_type": ctype, "failure_tags": [], "applicable_to": applicable, "tier": "batch",
        }

    def test_few_shot_eligible_filters(self):
        r = self._retriever_with_entries([])
        pos = self._mk("p1", "positive")
        neg = self._mk("n1", "negative")
        evl = self._mk("e1", "positive", applicable="eval")
        both = self._mk("b1", "positive", applicable="both")
        items = [pos, neg, evl, both]
        assert r._few_shot_eligible(items) == [pos, both]

    def test_negative_not_injected_but_retrievable(self):
        pos = self._mk("p1", "positive", text="a rainy rooftop duel in the neon district " * 6)
        neg = self._mk("n1", "negative", text="a rainy rooftop duel in the neon district, badly lit " * 6)
        r = self._retriever_with_entries([pos, neg])
        # 检索路径仍可访问负样本
        fallback = r.keyword_fallback("rainy rooftop neon", "generic_video", top_k=5)
        assert any(e["id"] == "n1" for e in fallback)
        # few-shot 注入路径排除负样本
        section = r._format_section(r._few_shot_eligible(fallback))
        assert "p1" in section
        assert "n1" not in section

    def test_eval_only_not_injected(self):
        evl = self._mk("e1", "positive", applicable="eval", text="a dry canyon crossing " * 6)
        r = self._retriever_with_entries([evl])
        fallback = r.keyword_fallback("dry canyon", "generic_video", top_k=5)
        assert r._few_shot_eligible(fallback) == []


class TestEvaluateNegatives:
    def test_report_structure_and_recall(self):
        res = evaluate_negatives(FAILURE_SAMPLES, length_strict=False)
        assert res["totals"]["samples"] == len(FAILURE_SAMPLES)
        assert res["totals"]["evaluated"] == len(FAILURE_SAMPLES)
        # 可判定模式全召回、零误报（资产与评估器对齐）
        assert res["totals"]["recall"] == 1.0
        assert res["totals"]["misses"] == 0
        assert res["totals"]["false_positives"] == 0
        # 未启用 gated 规则正确报告（不污染召回分母）
        assert "silhouette_break" in res["totals"]["uncovered_tags"]
        assert res["patterns"]["exposure_break"]["recall"] == 1.0
        assert res["patterns"]["silhouette_break"]["covered"] is False
        assert res["patterns"]["silhouette_break"]["recall"] is None

    def test_miss_details_readable(self):
        res = evaluate_negatives(
            [
                {
                    "id": "custom-fail",
                    "prompt_text": (
                        "DURATION: 8s. ASPECT RATIO: 16:9. ONE CONTINUOUS SHOT - the vault "
                        "door grinds open, dust swirling, sfx echoing through the chamber, the "
                        "frame holds until the stillness lock. FINAL FRAME: palette locked."
                    ),
                    "failure_tags": ["missing_trailer"],
                    "tier": "refined",
                }
            ],
            length_strict=False,
        )
        d = res["details"][0]
        assert d["id"] == "custom-fail"
        assert d["missed"] == ["missing_trailer"]      # 漏检明细可读
        assert res["patterns"]["missing_trailer"]["recall"] == 0.0

    def test_evaluate_negatives_isolated(self):
        # 常规评分路径零影响：独立入口不修改 evaluate/select_best 行为
        from video_prompt_engine.evaluator import evaluate, select_best
        r1 = evaluate("short", {}, "", "en", tier="batch")
        best, meta, score = select_best([("a short one", {}), ("A cinematic wide shot. " * 8, {})], "", "en", tier="batch")
        assert 0 <= r1["score"] <= 100
        assert best and 0 <= score <= 100
        res = evaluate_negatives(FAILURE_SAMPLES)
        assert "patterns" in res and "details" in res