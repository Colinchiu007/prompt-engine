"""506 案例解析测试 — 验证 awesome-gpt-image-2 数据解析"""
import json
import os
import tempfile
from pathlib import Path


class TestCasesJsonParsing:
    """测试 cases.json 解析和 PromptEntry 转换."""

    @staticmethod
    def _create_sample_cases() -> dict:
        return {
            "repository": "awesome-gpt-image-2",
            "totalCases": 3,
            "categories": ["Architecture", "Brand"],
            "styles": ["3D", "Illustration"],
            "scenes": ["Creative", "Tech"],
            "cases": [
                {
                    "id": 1,
                    "title": "Futuristic Cityscape",
                    "prompt": "A futuristic city at sunset with neon lights and flying cars",
                    "image": "https://example.com/img1.jpg",
                    "category": "Architecture",
                    "styles": ["3D", "Architecture"],
                    "scenes": ["Creative", "Tech"],
                    "sourceUrl": "https://github.com/example/1",
                    "featured": True,
                },
                {
                    "id": 2,
                    "title": "Modern Logo Design",
                    "prompt": "Minimalist geometric logo with gold accents on dark background",
                    "image": "https://example.com/img2.jpg",
                    "category": "Brand",
                    "styles": ["Brand", "Minimalist"],
                    "scenes": ["Commerce"],
                    "sourceUrl": "https://github.com/example/2",
                    "featured": True,
                },
                {
                    "id": 3,
                    "title": "Data Dashboard UI",
                    "prompt": "Clean analytics dashboard with charts, graphs, and data tables",
                    "image": "https://example.com/img3.jpg",
                    "category": "Charts",
                    "styles": ["Charts", "UI"],
                    "scenes": ["Tech"],
                    "sourceUrl": "https://github.com/example/3",
                    "featured": False,
                },
            ],
        }

    def test_parse_cases_json_structure(self):
        """验证 cases.json 基本结构."""
        data = self._create_sample_cases()
        assert "cases" in data
        assert "categories" in data
        assert "styles" in data
        assert "scenes" in data
        assert len(data["cases"]) == 3

    def test_case_has_required_fields(self):
        """每个 case 必须含 id, title, prompt, category."""
        data = self._create_sample_cases()
        for case in data["cases"]:
            assert "id" in case
            assert "title" in case
            assert "prompt" in case
            assert "category" in case
            assert len(case["prompt"]) > 10

    def test_convert_to_prompt_entry(self):
        """验证 case → PromptEntry 转换."""
        from prompt_engine.knowledge.loader import PromptEntry

        data = self._create_sample_cases()
        entries = []
        for case in data["cases"]:
            entry = PromptEntry(
                id=f"gptimg2-{case['id']}",
                title=case.get("title", ""),
                prompt_text=case.get("prompt", ""),
                description=f"GPT-Image2 case: {case.get('category', '')}",
                categories=[case.get("category", "")] + case.get("styles", []),
                platform="generic",
                quality_score=8,
            )
            entries.append(entry)

        assert len(entries) == 3
        assert entries[0].id == "gptimg2-1"
        assert "Architecture" in entries[0].categories
        assert entries[0].quality_score == 8
        assert len(entries[0].prompt_text) > 10

    def test_inject_to_vector_store(self):
        """验证注入 RAG 知识库后能检索到."""
        from prompt_engine.knowledge.vector_store import PromptVectorStore
        from prompt_engine.knowledge.loader import PromptEntry
        import tempfile, os

        with tempfile.TemporaryDirectory() as tmpdir:
            store = PromptVectorStore(tmpdir)
            data = self._create_sample_cases()
            entries = []
            for case in data["cases"]:
                entry = PromptEntry(
                    id=f"gptimg2-{case['id']}",
                    title=case.get("title", ""),
                    prompt_text=case.get("prompt", ""),
                    description=f"GPT-Image2 case: {case.get('category', '')}",
                    categories=[case.get("category", "")] + case.get("styles", []),
                    platform="generic",
                    quality_score=8,
                )
                entries.append(entry)

            store.add_prompts(entries)
            assert store.count == 3

            # 检索验证
            results = store.search("futuristic city", top_k=2)
            assert len(results) >= 1
            assert "futuristic" in results[0]["document"].lower()
