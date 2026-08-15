"""视频知识库构建：种子 → TF-IDF 索引（独立 video_prompts_db）。"""
from pathlib import Path

from video_prompt_engine.config import load_config
from video_prompt_engine.knowledge.loader import load_seed_video_prompts
from video_prompt_engine.knowledge.vector_store import PromptVectorStore


def build_knowledge_base(
    config_path: str | None = None, seed_path: str | None = None, extra_seed_path: str | None = None,
) -> int:
    cfg = load_config(config_path)
    kb_cfg = cfg.get("knowledge", {})
    if not seed_path:
        seed_path = str(Path(__file__).parent / "seed_video_prompts.json")
    if extra_seed_path is None:
        extra_seed_path = str(Path(__file__).parent / "seed_higgsfield_prompts.json")
    persist = kb_cfg.get("persist_dir", "video_prompts_db")
    persist_dir = Path(persist)
    if not persist_dir.is_absolute():
        persist_dir = Path(__file__).parent.parent.parent / persist_dir

    extra = Path(extra_seed_path)
    extra_paths: list[Path] = [extra] if extra.exists() else []
    for cand in (Path(__file__).parent / "corpus_index.json", Path(__file__).parent / "seed_failure_samples.json"):
        if cand.exists():
            extra_paths.append(cand)
    prompts = load_seed_video_prompts(Path(seed_path), extra_paths)
    # video-corpus-expansion 组4：负样本不进向量索引（few-shot 注入不需要；检索语义由注入前过滤兜底）
    prompts = [p for p in prompts if p.corpus_type != "negative"]
    store = PromptVectorStore(persist_dir)
    store.clear()
    store.add_prompts(prompts)
    return store.count


if __name__ == "__main__":
    n = build_knowledge_base()
    print(f"video knowledge base built: {n} entries")
