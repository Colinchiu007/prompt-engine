"""从 awesome-gpt-image-2 的 cases.json 注入 RAG 种子数据。

Usage:
    python examples/seed_rag_from_gptimage2.py

从 research/awesome-gpt-image-2/src/data/cases.json 读取 506 个案例，
转换为 PromptEntry 后注入到 prompt-engine 的 RAG 向量库。
"""
import json
import sys
from pathlib import Path

# 尝试多个路径找到 cases.json
CANDIDATE_PATHS = [
    Path(__file__).parent.parent / "research" / "awesome-gpt-image-2" / "src" / "data" / "cases.json",
    Path(__file__).parent.parent / "research" / "awesome-gpt-image-2" / "data" / "cases.json",
]


def find_cases_json() -> Path:
    for p in CANDIDATE_PATHS:
        if p.exists():
            return p
    # 如果不存在，输出提示
    print("cases.json not found. Please clone awesome-gpt-image-2 first:")
    print("  git clone --depth 1 https://github.com/freestylefly/awesome-gpt-image-2.git research/awesome-gpt-image-2")
    sys.exit(1)


def load_cases(path: Path) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("cases", [])


def convert_to_entries(cases: list[dict]) -> list:
    from prompt_engine.knowledge.loader import PromptEntry

    entries = []
    for case in cases:
        entry = PromptEntry(
            id=f"gptimg2-{case.get('id', 'unknown')}",
            title=case.get("title", f"GPT-Image2 Case {case.get('id', '')}"),
            prompt_text=case.get("prompt", ""),
            description=f"GPT-Image2 case - Category: {case.get('category', '')}, "
                       f"Styles: {', '.join(case.get('styles', []))}",
            categories=[case.get("category", "")] + case.get("styles", []),
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

    # 验证检索
    print("\nVerification searches:")
    for query in ["futuristic city", "portrait photography", "brand logo"]:
        results = store.search(query, top_k=2)
        if results:
            print(f"  '{query}' → {len(results)} results (top: {results[0]['document'][:60]}...)")
        else:
            print(f"  '{query}' → no results")

    return store.count


def main():
    path = find_cases_json()
    print(f"Loading cases from: {path}")
    cases = load_cases(path)
    print(f"Found {len(cases)} cases")

    entries = convert_to_entries(cases)
    total = seed_rag(entries)
    print(f"\n✅ RAG seeded with {total} total entries.")


if __name__ == "__main__":
    main()
