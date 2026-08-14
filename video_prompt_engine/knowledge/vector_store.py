"""视频知识库 TF-IDF 向量存储 — 复用共享内核实现（prompt_engine_core.vector_store）。

- 独立持久化目录（video_prompts_db）由调用方传入，不加载图片种子
- 模块路径保持不变，既有导入方（rag_retriever / knowledge.build）零改动
- 检索语义与持久化格式（index.json）与 core 完全一致
"""
from prompt_engine_core.vector_store import PromptVectorStore

__all__ = ["PromptVectorStore"]
