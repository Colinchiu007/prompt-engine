"""视频知识库构建：种子 → TF-IDF 索引（独立 video_prompts_db）。"""
from pathlib import Path

from video_prompt_engine.config import load_config
from video_prompt_engine.knowledge.loader import load_seed_video_prompts
from video_prompt_engine.knowledge.vector_store import PromptVectorStore


def build_knowledge_base(config_path: str | None = None, seed_path: str | None = None) -> int:
    cfg = load_config(config_path)
    kb_cfg = cfg.get("knowledge", {})
    if not seed_path:
        seed_path = str(Path(__file__).parent / "seed_video_prompts.json")
    persist = kb_cfg.get("persist_dir", "video_prompts_db")
    persist_dir = Path(persist)
    if not persist_dir.is_absolute():
        persist_dir = Path(__file__).parent.parent.parent / persist_dir

    prompts = load_seed_video_prompts(Path(seed_path))
    store = PromptVectorStore(persist_dir)
    store.clear()
    store.add_prompts(prompts)
    return store.count


if __name__ == "__main__":
    n = build_knowledge_base()
    print(f"video knowledge base built: {n} entries")
