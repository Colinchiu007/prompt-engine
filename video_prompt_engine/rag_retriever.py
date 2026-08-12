"""视频 RAG 检索 — 知识库初始化 + few-shot 注入 + 关键词命中兜底（独立实现）。"""
from __future__ import annotations

import logging
from pathlib import Path

from video_prompt_engine.models import VideoOptimizeRequest

logger = logging.getLogger(__name__)


class VideoRAGRetriever:
    """视频知识库检索：向量相似（platform 过滤）→ 无命中时关键词兜底（匹配平台种子 top_k）。"""

    def __init__(self, config: dict):
        self._config = config
        self._vector_store = None
        self._seed_entries: list[dict] = []
        self._init_knowledge()

    def _seed_path(self) -> Path:
        return Path(__file__).parent / "knowledge" / "seed_video_prompts.json"

    def _init_knowledge(self):
        kb_cfg = self._config.get("knowledge", {})
        if not kb_cfg.get("enabled", True):
            return
        # 加载种子（关键词兜底用；向量库不存在时也保留种子兜底能力）
        try:
            from video_prompt_engine.knowledge.loader import load_seed_video_prompts
            seeds = load_seed_video_prompts(self._seed_path())
            self._seed_entries = [
                {
                    "id": s.id, "title": s.title, "description": s.description,
                    "document": s.prompt_text, "language": s.language,
                    "platform": s.platform, "style": s.style,
                    "categories": s.categories, "quality_score": s.quality_score,
                    "source": s.source,
                }
                for s in seeds
            ]
        except Exception as e:
            logger.warning("video seeds load failed: %s", e)
        persist = kb_cfg.get("persist_dir", "video_prompts_db")
        persist_dir = Path(persist)
        if not persist_dir.is_absolute():
            persist_dir = Path(__file__).parent.parent.parent / persist_dir
        if not persist_dir.exists():
            logger.info("video knowledge base not built yet; run build_knowledge_base()")
            return
        try:
            from video_prompt_engine.knowledge.vector_store import PromptVectorStore
            self._vector_store = PromptVectorStore(persist_dir)
        except Exception:
            pass

    def _top_k(self) -> int:
        return int(self._config.get("knowledge", {}).get("retrieval", {}).get("top_k", 3))

    def keyword_fallback(self, query: str, platform: str, top_k: int = 3) -> list[dict]:
        """向量检索无命中时：按关键词命中匹配平台种子（平台精确 > 通用种子），返回 top_k。"""
        if not self._seed_entries:
            return []
        q = str(query or "").lower()
        # 简单分词：英文词 + 中文 2-6 字片段
        import re
        zh_chunks = re.findall(r"[\u4e00-\u9fff]{2,6}", q)
        en_words = [w for w in re.findall(r"[a-z0-9]{2,}", q) if len(w) > 2]
        if not zh_chunks and not en_words:
            return []
        platform = str(platform or "generic_video")

        def _hit(entry: dict) -> int:
            text = " ".join([
                str(entry.get("title") or ""), str(entry.get("description") or ""),
                str(entry.get("document") or ""), " ".join(entry.get("categories") or []),
            ]).lower()
            score = 0
            for c in zh_chunks:
                if c in text:
                    score += 2
            for w in en_words:
                if w in text:
                    score += 1
            return score

        scored = []
        for entry in self._seed_entries:
            if entry.get("platform") != platform and entry.get("platform") != "generic_video":
                continue
            s = _hit(entry)
            if s > 0:
                scored.append((s, entry))
        if not scored:
            return []
        scored.sort(key=lambda x: x[0], reverse=True)
        return [dict(e, score=round(s / max(1, len(zh_chunks) + len(en_words)), 2)) for s, e in scored[:top_k]]

    def _format_section(self, items: list[dict]) -> str:
        if not items:
            return ""
        section = "\n\n## 高质量视频参考示例（请参考这些 prompt 的风格和结构）:\n"
        for i, item in enumerate(items, 1):
            title = item.get("title") or f"示例 {i}"
            section += f"\n### 参考 {i}: {title}\n```\n{item['document']}\n```\n"
        return section

    def retrieve_few_shot(self, request: VideoOptimizeRequest, platform: str | None = None, language: str = "en") -> str:
        query = f"{request.style + ' ' if request.style else ''}{request.prompt}"
        top_k = self._top_k()
        platform = platform or (request.platform.value if hasattr(request.platform, "value") else str(request.platform))
        if self._vector_store:
            try:
                items = self._vector_store.search(query=query, top_k=top_k, platform=platform)
                if items:
                    return self._format_section(items)
            except Exception as e:
                logger.error("video RAG retrieval failed: %s", e)
        # 向量无命中 → 关键词兜底（匹配平台种子）
        try:
            items = self.keyword_fallback(query, platform, top_k)
            if items:
                logger.info("video RAG keyword fallback hit %d seed(s) for platform=%s", len(items), platform)
                return self._format_section(items)
        except Exception as e:
            logger.error("video RAG keyword fallback failed: %s", e)
        return ""
