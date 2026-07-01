#!/usr/bin/env python3
"""加载知识图谱导出的 RAG 知识文档到 prompt-engine 向量库

Usage:
  python prompt_engine/knowledge/load_graph_knowledge.py                          # 加载到向量库
  python prompt_engine/knowledge/load_graph_knowledge.py --dry-run               # 预览不写入
  python prompt_engine/knowledge/load_graph_knowledge.py --rebuild               # 重建索引
"""

import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from prompt_engine.knowledge.loader import PromptEntry
from prompt_engine.knowledge.vector_store import PromptVectorStore


def load_knowledge(path: str) -> list[PromptEntry]:
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    entries = []
    for i, item in enumerate(raw):
        entries.append(PromptEntry(
            id=f"graph-kb-{i:04d}",
            title=item.get("title", ""),
            description=item.get("description", ""),
            prompt_text=item["prompt"],
            language=item.get("language", "zh"),
            categories=item.get("categories", ["knowledge-graph"]),
            platform=item.get("platform", "generic"),
            style=item.get("style", "reference"),
            quality_score=item.get("quality_score", 7),
        ))
    return entries


def main():
    parser = argparse.ArgumentParser(description="Load graph knowledge into prompt-engine vector store")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument("--rebuild", action="store_true", help="Clear existing index before loading")
    args = parser.parse_args()

    kb_path = Path(__file__).parent / "graph_knowledge.json"
    if not kb_path.exists():
        print(f"Error: {kb_path} not found. Run export_graph_knowledge.py first.")
        sys.exit(1)

    entries = load_knowledge(str(kb_path))
    print(f"Loaded {len(entries)} knowledge entries from {kb_path.name}")

    if args.dry_run:
        print(f"\nSample entry:")
        e = entries[0]
        print(f"  Title: {e.title}")
        print(f"  Categories: {e.categories}")
        print(f"  Content: {e.prompt_text[:150]}...")
        print(f"\nDone (dry-run, no changes written)")
        return

    persist_dir = str(Path(__file__).parent.parent.parent / "prompts_db")
    store = PromptVectorStore(persist_dir)

    if args.rebuild:
        store.clear()
        print("Index cleared (rebuild mode)")

    store.add_prompts(entries)
    print(f"Vector store now has {store.count} entries")

    test = store.search("architecture", top_k=3)
    if test:
        print(f"\nVerification search for 'architecture':")
        for r in test:
            print(f"  [{r['score']:.3f}] {r['metadata']['title']}")
    print("Done.")


if __name__ == "__main__":
    main()
