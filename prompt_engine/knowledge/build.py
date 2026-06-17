"""知识库构建脚本 — 从种子数据构建向量库（TF-IDF）"""
import json
from pathlib import Path
from prompt_engine.config import load_config
from prompt_engine.knowledge.loader import PromptEntry
from prompt_engine.knowledge.vector_store import PromptVectorStore


def load_seed_prompts(seed_path: str) -> list[PromptEntry]:
    path = Path(seed_path)
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    entries = []
    for i, item in enumerate(raw):
        entries.append(PromptEntry(
            id=f"seed-{i:04d}",
            title=item.get("title", ""),
            description=item.get("description", ""),
            prompt_text=item["prompt"],
            language=item.get("language", "en"),
            categories=item.get("categories", []),
            platform=item.get("platform", "generic"),
            style=item.get("style", ""),
            quality_score=item.get("quality_score", 5),
        ))
    return entries


def build_knowledge_base(config_path: str | None = None, seed_path: str | None = None):
    config = load_config(config_path)
    kb_cfg = config.get("knowledge", {})

    if not seed_path:
        seed_path = str(Path(__file__).parent / "seed_prompts.json")

    print(f"📦 加载种子数据: {seed_path}")
    prompts = load_seed_prompts(seed_path)
    print(f"   共 {len(prompts)} 条")

    persist_dir = kb_cfg.get("persist_dir", "./prompts_db")
    if not Path(persist_dir).is_absolute():
        persist_dir = str(Path(__file__).parent.parent / persist_dir)

    print(f"⚡ 构建 TF-IDF 索引: {persist_dir}")
    store = PromptVectorStore(persist_dir)
    store.clear()
    store.add_prompts(prompts)
    print(f"   共 {store.count} 条索引")

    # 验证检索
    test = store.search("cat on windowsill", top_k=1)
    if test:
        print(f"   ✅ 检索验证通过: {test[0]['metadata']['title']}")
    else:
        print("   ⚠️ 检索无结果")

    print("✅ 知识库构建完成")


if __name__ == "__main__":
    build_knowledge_base()