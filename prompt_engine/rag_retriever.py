"""RAG retrieval — knowledge base init + few-shot prompt retrieval.

Extracted from optimizer.py God Class refactoring (Phase 1).
"""

import logging
from pathlib import Path
from typing import Optional

from prompt_engine.models import OptimizeRequest

logger = logging.getLogger(__name__)


class RAGRetriever:
    """RAG 知识库初始化与 few-shot 检索"""

    def __init__(self, config: dict):
        self._config = config
        self._vector_store = None
        self._init_knowledge()

    def _init_knowledge(self) -> None:
        """初始化 RAG 知识库（如果启用）"""
        kb_cfg = self._config.get("knowledge", {})
        if not kb_cfg.get("enabled", True):
            return

        persist_dir = kb_cfg.get("persist_dir", "./prompts_db")
        if not Path(persist_dir).is_absolute():
            persist_dir = str(Path(__file__).parent.parent / persist_dir)

        store_path = Path(persist_dir)
        if not store_path.exists():
            return  # 向量库不存在，跳过（首次需运行 build）

        try:
            from prompt_engine.knowledge.vector_store import PromptVectorStore
            self._vector_store = PromptVectorStore(persist_dir)
        except Exception:
            pass  # chromadb 未安装或数据不存在，静默降级

    def retrieve_few_shot(self, request: OptimizeRequest) -> str:
        """检索相似 prompt 作为 few-shot 示例"""
        if not self._vector_store:
            return ""

        query = f"{request.style.value + ' ' if request.style else ''}{request.prompt}"
        kb_cfg = self._config.get("knowledge", {}).get("retrieval", {})
        top_k = kb_cfg.get("top_k", 3)
        try:
            items = self._vector_store.search(
                query=query,
                top_k=top_k,
                platform=request.platform.value,
            )
            if not items:
                return ""

            section = "\n\n## 高质量参考示例（请参考这些 prompt 的风格和结构）:\n"
            for i, item in enumerate(items, 1):
                meta = item.get("metadata", {})
                title = meta.get("title", f"示例 {i}")
                section += f"\n### 参考 {i}: {title}\n```\n{item['document']}\n```\n"
            return section
        except Exception as e:
            logger.error("RAG retrieval failed: %s", e)
            return ""
