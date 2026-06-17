"""gpt4o-image-prompts 数据解析测试"""
import json
import tempfile
from prompt_engine.knowledge.loader import PromptEntry


class TestGpt4oPromptsParsing:
    """测试 prompts.json 解析."""

    SAMPLE = {
        "generatedAt": "2026-01-04T09:13:50.143Z",
        "total": 3,
        "items": [
            {
                "id": 1050,
                "title": "3D风格的女子",
                "model": "Nano banana pro",
                "prompts": [
                    "A stylized 3D animated young woman leaning against a wall...",
                    "一位风格化的3D动画年轻女子倚靠在一面墙上...",
                ],
                "images": ["images/1050.jpeg"],
                "tags": ["illustration"],
                "source": {"name": "@user", "url": "https://x.com/user/status/1"},
            },
            {
                "id": 1049,
                "title": "角色设定草图",
                "model": "Nano banana pro",
                "prompts": [
                    "Character sheet sketch of a subject, featuring multiple angles...",
                    "人物设定草图...",
                ],
                "images": ["images/1049.jpeg"],
                "tags": ["character", "portrait"],
                "source": {"name": "@user2", "url": "https://x.com/user2/status/2"},
            },
            {
                "id": 1048,
                "title": "女性面部涂口红效果",
                "model": "Grok",
                "prompts": [
                    "Using the attached image as a motif, we generated a difference image...",
                    "我们以附图为模板...",
                ],
                "images": ["images/1048.jpeg"],
                "tags": ["fashion", "portrait"],
                "source": {"name": "@user3", "url": "https://x.com/user3/status/3"},
            },
        ],
    }

    def test_load_prompts_json_structure(self):
        data = self.SAMPLE
        assert "items" in data
        assert data["total"] == 3
        assert len(data["items"]) == 3

    def test_item_has_required_fields(self):
        for item in self.SAMPLE["items"]:
            assert "id" in item
            assert "title" in item
            assert "prompts" in item
            assert "tags" in item
            assert len(item["prompts"]) >= 2  # EN + ZH

    def test_convert_to_prompt_entry(self):
        entries = []
        for item in self.SAMPLE["items"]:
            texts = item.get("prompts", [])
            en_text = texts[0] if texts else ""
            zh_text = texts[1] if len(texts) > 1 else ""
            combined = en_text
            if zh_text:
                combined += f"\n{zh_text}"

            entry = PromptEntry(
                id=f"gpt4o-{item['id']}",
                title=item.get("title", ""),
                prompt_text=combined,
                description=f"GPT-4o prompt - Model: {item.get('model', '')}",
                categories=item.get("tags", []),
                platform="generic",
                quality_score=8,
            )
            entries.append(entry)

        assert len(entries) == 3
        assert entries[0].id == "gpt4o-1050"
        assert "illustration" in entries[0].categories
        assert "Nano banana pro" in entries[0].description
        assert "\n" in entries[0].prompt_text  # EN + ZH combined

    def test_inject_to_vector_store(self):
        from prompt_engine.knowledge.vector_store import PromptVectorStore
        import tempfile, os

        with tempfile.TemporaryDirectory() as tmpdir:
            store = PromptVectorStore(tmpdir)
            entries = []
            for item in self.SAMPLE["items"]:
                texts = item.get("prompts", [])
                en_text = texts[0] if texts else ""
                zh_text = texts[1] if len(texts) > 1 else ""
                combined = en_text
                if zh_text:
                    combined += f"\n{zh_text}"

                entry = PromptEntry(
                    id=f"gpt4o-{item['id']}",
                    title=item.get("title", ""),
                    prompt_text=combined,
                    description=f"GPT-4o prompt - Model: {item.get('model', '')}",
                    categories=item.get("tags", []),
                    platform="generic",
                    quality_score=8,
                )
                entries.append(entry)

            store.add_prompts(entries)
            assert store.count == 3

            # Search in EN
            results = store.search("stylized 3D animated", top_k=2)
            assert len(results) >= 1

            # Search in ZH
            results_zh = store.search("风格化 3D 动画", top_k=2)
            assert len(results_zh) >= 1
