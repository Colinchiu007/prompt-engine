"""从 gpt4o-image-prompts 的 prompts.json 注入 RAG 种子数据。

Usage:
    python examples/seed_rag_from_gpt4o_prompts.py

从 research/gpt4o-image-prompts/src/data/prompts.json 读取 1050 条
双语 prompt，转换为 PromptEntry 后注入到 prompt-engine 的 RAG 向量库。
"""
import json
import sys
from pathlib import Path

CANDIDATE_PATHS = [
    Path(__file__).parent.parent / "research" / "gpt4o-image-prompts" / "src" / "data" / "prompts.json",
]


def find_prompts_json() -> Path:
    for p in CANDIDATE_PATHS:
        if p.exists():
            return p
    print("prompts.json not found. Please clone gpt4o-image-prompts first:")
    print("  git clone --depth 1 https://github.com/songguoxs/gpt4o-image-prompts.git research/gpt4o-image-prompts")
    sys.exit(1)


def load_prompts(path: Path) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    items = data.get("items", [])
    print(f"Loaded {len(items)} prompts from {path}")
    return items


def convert_to_entries(prompts: list[dict]) -> list:
    from prompt_engine.knowledge.loader import PromptEntry

    entries = []
    for prompt in prompts:
        # Get the English prompt text (prefer EN over ZH for vector search)
        texts = prompt.get("prompts", [])
        en_text = texts[0] if texts else ""
        zh_text = texts[1] if len(texts) > 1 else ""

        # Combine EN and ZH for better search coverage
        combined_text = en_text
        if zh_text:
            combined_text += f"\n{zh_text}"

        # Tags as categories
        tags = prompt.get("tags", [])
        model = prompt.get("model", "unknown")

        entry = PromptEntry(
            id=f"gpt4o-{prompt.get('id', 'unknown')}",
            title=prompt.get("title", f"Prompt {prompt.get('id', '')}"),
            prompt_text=combined_text,
            description=f"GPT-4o prompt - Model: {model}, Tags: {', '.join(tags[:5])}",
            categories=tags if tags else ["general"],
            platform="generic",
            quality_score=8,
        )
        entries.append(entry)
    return entries


def seed_rag(entries: list, persist_dir: str = "./prompts_db") -> int:
    from prompt_engine.knowledge.vector_store import PromptVectorStore

    print(f"Loading {len(entries)} entries into RAG store at {persist_dir}...")
    store = PromptVectorStore(persist_dir)
    existing = store.count
    print(f"  Existing entries: {existing}")

    store.add_prompts(entries)
    print(f"  New entries: {len(entries)}")
    print(f"  Total: {store.count}")

    # Verify retrieval
    print("\nVerification searches:")
    for query in ["portrait photography", "landscape nature", "3d character"]:
        results = store.search(query, top_k=2)
        if results:
            print(f"  '{query}' → {len(results)} results (top: {results[0]['document'][:60]}...)")
        else:
            print(f"  '{query}' → no results")

    return store.count


def main():
    path = find_prompts_json()
    prompts = load_prompts(path)
    entries = convert_to_entries(prompts)
    total = seed_rag(entries)
    print(f"\n✅ RAG seeded with {total} total entries.")


if __name__ == "__main__":
    main()
