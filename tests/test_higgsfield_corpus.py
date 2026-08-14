"""Higgsfield 语料资产化（DEEP P2.9）+ 共享内核向量检索 O(n²) 修复回归测试。"""
import json
import tempfile
from collections import Counter
from pathlib import Path

import pytest

from prompt_engine_core.vector_store import PromptVectorStore, _tokenize
from video_prompt_engine.knowledge.loader import load_seed_video_prompts
from video_prompt_engine.rag_retriever import VideoRAGRetriever

_REPO = Path(__file__).parent.parent
_HG_PATH = _REPO / "video_prompt_engine" / "knowledge" / "seed_higgsfield_prompts.json"
_MAIN_PATH = _REPO / "video_prompt_engine" / "knowledge" / "seed_video_prompts.json"
_TIERS = {"tier:refined", "tier:batch", "tier:variant", "tier:asset"}


def _hg_entries() -> list[dict]:
    return json.loads(_HG_PATH.read_text(encoding="utf-8"))


class TestHiggsfieldSeedArtifact:
    """P2.9 产物：结构/平台白名单/tier 标签/幂等生成。"""

    def test_file_exists_and_is_list(self):
        assert _HG_PATH.exists(), "seed_higgsfield_prompts.json 缺失（先运行 scripts/build_higgsfield_seeds.py）"
        entries = _hg_entries()
        assert isinstance(entries, list)
        assert len(entries) >= 250  # 语料按 prompt_text 去重后 258 条（W5：同 prompt 多 job 参数变体不重复入库）

    def test_entry_schema(self):
        entries = _hg_entries()
        ids = set()
        for e in entries:
            assert len(e["prompt_text"]) > 50
            assert e["platform"] in ("seedance", "generic_video")
            assert e["language"] == "en"
            assert e["source"] == "higgsfield-corpus"
            assert e["id"].startswith("hg-") and e["id"] not in ids
            ids.add(e["id"])
            tiers = [c for c in e["categories"] if c.startswith("tier:")]
            assert len(tiers) == 1 and tiers[0] in _TIERS

    def test_tier_and_platform_coverage(self):
        entries = _hg_entries()
        tiers = Counter(c for e in entries for c in e["categories"] if c.startswith("tier:"))
        assert tiers["tier:refined"] >= 100  # 精修层（20KB 导演分镜单）全量入库
        assert tiers["tier:batch"] >= 100
        platforms = Counter(e["platform"] for e in entries)
        assert platforms["seedance"] >= 230  # seedance_2_0 参数画像 91%
        assert platforms["generic_video"] >= 20  # soul_cinematic/nano_banana 等

    def test_no_image_model_leak(self):
        entries = _hg_entries()
        models = set(c for e in entries for c in e["categories"] if c.startswith("model:"))
        assert not any(m in ("model:imagegen_2_0", "model:gpt_image_2", "model:text2image_soul_v2") for m in models)

    def test_regeneration_deterministic(self):
        """重建产物与提交产物一致（脚本幂等 + 排序稳定）。"""
        import subprocess, sys
        out = Path(tempfile.mkdtemp()) / "regen.json"
        r = subprocess.run(
            [sys.executable, str(_REPO / "scripts" / "build_higgsfield_seeds.py"), str(Path(r"D:\Temp\hg-corpus")), str(out)],
            capture_output=True, text=True, timeout=120,
        )
        if r.returncode != 0 or not out.exists():
            pytest.skip(f"corpus 不可用，跳过确定性校验: {r.stderr[:200]}")
        before = json.dumps(_hg_entries(), ensure_ascii=False, sort_keys=True)
        after = json.dumps(json.loads(out.read_text(encoding="utf-8")), ensure_ascii=False, sort_keys=True)
        assert before == after


class TestLoaderMerge:
    def test_loader_merges_extra(self, tmp_path):
        main = tmp_path / "main.json"
        main.write_text(json.dumps([{"id": "m1", "prompt_text": "hello world"}]), encoding="utf-8")
        extra = tmp_path / "extra.json"
        extra.write_text(json.dumps([{"id": "x1", "prompt_text": "long enough prompt text", "platform": "seedance"}]), encoding="utf-8")
        entries = load_seed_video_prompts(main, extra)
        assert len(entries) == 2
        assert entries[1].platform == "seedance"  # 显式平台保留

    def test_loader_single_arg_backward_compat(self, tmp_path):
        main = tmp_path / "main.json"
        main.write_text(json.dumps([{"prompt_text": "hello"}]), encoding="utf-8")
        entries = load_seed_video_prompts(main)
        assert len(entries) == 1
        assert entries[0].platform == "generic_video"  # 缺失回退

    def test_loader_missing_extra_skipped(self):
        main = Path(tempfile.mkdtemp()) / "main.json"
        main.write_text(json.dumps([{"prompt_text": "hello"}]), encoding="utf-8")
        entries = load_seed_video_prompts(main, main.parent / "nope.json")
        assert len(entries) == 1

    def test_full_higgsfield_file_loads(self):
        entries = load_seed_video_prompts(_MAIN_PATH, _HG_PATH)
        assert len(entries) >= 390  # 140 自研种子 + 258 去重后语料
        assert any(e.id.startswith("hg-") for e in entries)


class TestRetrieverMergedSeeds:
    def _retriever(self):
        cfg = {"knowledge": {"enabled": True, "persist_dir": str(Path(tempfile.mkdtemp()) / "no-index"), "retrieval": {"top_k": 3}}}
        return VideoRAGRetriever(cfg)

    def test_retriever_loads_higgsfield_seeds(self):
        rr = self._retriever()
        assert len(rr._seed_entries) >= 250
        hg = [e for e in rr._seed_entries if str(e.get("source")) == "higgsfield-corpus"]
        assert len(hg) >= 250

    def test_keyword_fallback_platform_whitelist_intact(self):
        rr = self._retriever()
        items = rr.keyword_fallback("运镜 广告 分镜编排", "seedance")
        assert items
        assert all(i.get("platform") in ("seedance", "generic_video") for i in items)
        assert any("运镜" in str(i.get("document", "")) or "广告" in str(i.get("document", "")) for i in items)


class TestFormatSectionBudget:
    """C2 修复：超长条目截断注入而非丢弃；预算内整段不超限；前缀去重。"""

    def _item(self, doc, title="t"):
        return {"id": "i", "title": title, "document": doc, "platform": "seedance"}

    def test_long_doc_truncated_within_budget(self):
        from video_prompt_engine.rag_retriever import VideoRAGRetriever
        rr = VideoRAGRetriever.__new__(VideoRAGRetriever)
        doc = "A" * 20000
        section = rr._format_section([self._item(doc)], budget=6000, per_item_cap=5000)
        assert "…[truncated]" in section
        assert len(section) <= 6000 + 200
        assert "A" * 5000 in section  # 截断头保留

    def test_all_short_docs_injected_until_budget(self):
        """W2 回归：条数只由 budget 约束，不设 3 条硬上限。"""
        from video_prompt_engine.rag_retriever import VideoRAGRetriever
        rr = VideoRAGRetriever.__new__(VideoRAGRetriever)
        items = [self._item(f"prompt {i} " + "B" * 500, f"t{i}") for i in range(5)]
        section = rr._format_section(items, budget=6000, per_item_cap=5000)
        assert section.count("### 参考") == 5
        assert "参考 1" in section and "参考 5" in section
        assert len(section) <= 6000 + 200

    def test_budget_cutoff_stops_at_first_exceeding(self):
        """预算截断回归：第 4 条放不下时注入前 3 条并停止。"""
        from video_prompt_engine.rag_retriever import VideoRAGRetriever
        rr = VideoRAGRetriever.__new__(VideoRAGRetriever)
        items = [self._item(f"{i}" + "C" * 400, f"t{i}") for i in range(4)]
        section = rr._format_section(items, budget=1400, per_item_cap=5000)
        assert section.count("### 参考") == 3
        assert "参考 4" not in section

    def test_tiny_budget_injects_at_least_one(self):
        """W1 回归：预算小于单条上限/最小开销时也保证注入至少一条。"""
        from video_prompt_engine.rag_retriever import VideoRAGRetriever
        rr = VideoRAGRetriever.__new__(VideoRAGRetriever)
        doc = "D" * 2000
        section = rr._format_section([self._item(doc)], budget=100, per_item_cap=5000)
        assert section != ""
        assert "参考 1" in section
        assert "…[truncated]" in section  # 正文按预算截断而非整条丢弃

    def test_prefix_dedupe_keeps_first_only(self):
        from video_prompt_engine.rag_retriever import VideoRAGRetriever
        rr = VideoRAGRetriever.__new__(VideoRAGRetriever)
        same_prefix = "P" * 250
        items = [self._item(same_prefix + " variant A", "a"), self._item(same_prefix + " variant B", "b")]
        section = rr._format_section(items, budget=6000, per_item_cap=5000)
        assert section.count("### 参考") == 1
        assert "variant A" in section and "variant B" not in section

    def test_empty_items_returns_empty(self):
        from video_prompt_engine.rag_retriever import VideoRAGRetriever
        rr = VideoRAGRetriever.__new__(VideoRAGRetriever)
        assert rr._format_section([]) == ""


class TestVectorStoreO2Fix:
    """共享内核 O(n²) 修复：结果与旧算法逐位一致 + 种子变更后索引重建。"""

    DOCS = [
        ("d1", "a cat running through a neon cyberpunk street at night", "seedance"),
        ("d2", "sunset over mountain with golden light and birds", "generic_video"),
        ("d3", "neon city street with flying cars and holograms", "seedance"),
        ("d4", "a cat sitting on a windowsill watching rain", "seedance"),
        ("d5", "underwater coral reef with colorful fish", "generic_video"),
    ]

    @staticmethod
    def _entry(doc_id, text, platform):
        from types import SimpleNamespace
        return SimpleNamespace(
            id=doc_id, title=doc_id, description="", prompt_text=text, language="en",
            platform=platform, style="", categories=[], quality_score=5, source="",
        )

    def _store(self, tmp_path):
        store = PromptVectorStore(tmp_path)
        store.add_prompts([self._entry(*d) for d in self.DOCS])
        return store

    def _old_search(self, store, query, top_k=3, platform=None):
        """旧算法参考实现（仍保留的 _tfidf/_cosine 路径）。"""
        qvec = store._tfidf(_tokenize(query))
        scored = []
        for doc in store._docs:
            if platform and doc.get("platform") != platform and doc.get("platform") != "generic_video":
                continue
            s = store._cosine(qvec, store._tfidf(_tokenize(doc.get("document", ""))))
            if s > 0:
                scored.append((s, doc))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [dict(d, score=round(s, 4)) for s, d in scored[:top_k]]

    def test_new_search_matches_old_exactly(self, tmp_path):
        store = self._store(tmp_path)
        query = "a cat running through a neon cyberpunk street"
        new = store.search(query, top_k=3)
        old = self._old_search(store, query, top_k=3)
        assert [r["id"] for r in new] == [r["id"] for r in old]
        assert [r["score"] for r in new] == [r["score"] for r in old]

    def test_platform_filter_preserved(self, tmp_path):
        store = self._store(tmp_path)
        res = store.search("neon street", top_k=5, platform="seedance")
        assert res and all(r["platform"] in ("seedance", "generic_video") for r in res)

    def test_index_rebuilt_after_add(self, tmp_path):
        store = self._store(tmp_path)
        store.add_prompts([self._entry("d6", "a cat chasing neon laser pointer in the street", "seedance")])
        res = store.search("neon cat street", top_k=3)
        ids = [r["id"] for r in res]
        assert "d6" in ids  # 增量后索引必须包含新文档

    def test_clear_then_add_rebuilds(self, tmp_path):
        store = self._store(tmp_path)
        store.clear()
        assert store.count == 0
        store.add_prompts([self._entry("d7", "mountain lake mirror reflection", "generic_video")])
        res = store.search("mountain lake", top_k=3)
        assert [r["id"] for r in res] == ["d7"]

    def test_full_corpus_index_builds_and_searches(self, tmp_path):
        """730 条（140 自研 + 590 语料）全量建索引 + 检索冒烟（修复前 O(n²) 需 >2 分钟，修复后秒级）。"""
        import time
        from prompt_engine_core.knowledge import load_seed_entries
        seeds = load_seed_entries(_MAIN_PATH, default_platform="generic_video")
        extra = load_seed_entries(_HG_PATH, default_platform="generic_video")
        store = PromptVectorStore(tmp_path)
        store.add_prompts(seeds + extra)
        assert store.count == len(seeds) + len(extra)
        t0 = time.perf_counter()
        res = store.search("a dramatic fight scene with slow motion camera", top_k=3)
        elapsed = time.perf_counter() - t0
        assert len(res) > 0
        assert elapsed < 10  # 修复后毫秒级；旧实现此规模需数分钟


class TestIndexVersioning:
    """W4：index.json 版本化 + 历史裸列表兼容 + 陈旧索引检测。"""

    def test_save_writes_versioned_payload(self, tmp_path):
        store = PromptVectorStore(tmp_path)
        store.add_prompts([TestVectorStoreO2Fix._entry("d1", "a cat in the rain", "seedance")])
        payload = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
        assert payload["version"] == 2
        assert len(payload["docs"]) == 1

    def test_versioned_index_loads_with_schema_version(self, tmp_path):
        (tmp_path / "index.json").write_text(
            json.dumps({"version": 2, "docs": [{"id": "d1", "document": "a cat"}]}), encoding="utf-8",
        )
        store = PromptVectorStore(tmp_path)
        assert store.schema_version == 2
        assert store.count == 1

    def test_legacy_list_index_loads_as_v1(self, tmp_path):
        (tmp_path / "index.json").write_text(
            json.dumps([{"id": "d1", "document": "a cat"}]), encoding="utf-8",
        )
        store = PromptVectorStore(tmp_path)
        assert store.schema_version == 1  # 历史裸列表格式识别为 v1，不崩
        assert store.count == 1
        assert len(store.search("cat")) == 1

    def test_stale_index_detection_logs_warning(self, tmp_path, caplog):
        """陈旧索引（向量条数 < 种子条数）启动时告警，提示重跑 build_knowledge_base()。"""
        import logging
        from video_prompt_engine.rag_retriever import VideoRAGRetriever
        stale = PromptVectorStore(tmp_path)
        stale.add_prompts([TestVectorStoreO2Fix._entry("old1", "old prompt only", "seedance")])
        cfg = {"knowledge": {"enabled": True, "persist_dir": str(tmp_path), "retrieval": {"top_k": 3}}}
        with caplog.at_level(logging.WARNING, logger="video_prompt_engine.rag_retriever"):
            rr = VideoRAGRetriever(cfg)
        assert rr._vector_store is not None
        assert any("build_knowledge_base" in r.message for r in caplog.records)