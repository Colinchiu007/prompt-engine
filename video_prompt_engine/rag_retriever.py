"""视频 RAG 检索 — 知识库初始化 + few-shot 注入（独立实现）。"""
from __future__ import annotations

import logging
from pathlib import Path

from video_prompt_engine.models import VideoOptimizeRequest

logger = logging.getLogger(__name__)


class VideoRAGRetriever:
    """视频知识库检索：platform 过滤 + top_k few-shot。"""

    def __init__(self, config: dict):
        self._config = config
        self._vector_store = None
        self._init_knowledge()

    def _init_knowledge(self):
        kb_cfg = self._config.get("knowledge", {})
        if not kb_cfg.get("enabled", True):
            return
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

    def retrieve_few_shot(self, request: VideoOptimizeRequest) -> str:
        if not self._vector_store:
            return ""
        query = f"{request.style + ' ' if request.style else ''}{request.prompt}"
        top_k = self._config.get("knowledge", {}).get("retrieval", {}).get("top_k", 3)
        try:
            items = self._vector_store.search(query=query, top_k=top_k, platform=request.platform.value if hasattr(request.platform, "value") else str(request.platform))
            if not items:
                return ""
            section = "\n\n## 高质量视频参考示例（请参考这些 prompt 的风格和结构）:\n"
            for i, item in enumerate(items, 1):
                title = item.get("title", f"示例 {i}")
                section += f"\n### 参考 {i}: {title}\n```\n{item['document']}\n```\n"
            return section
        except Exception as e:
            logger.error("video RAG retrieval failed: %s", e)
            return ""
