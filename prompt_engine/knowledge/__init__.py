"""知识库 — RAG 引擎（可选模块）
通过 ChromaDB 语义检索，将相似优质 prompt 注入 LLM 上下文作为 few-shot 示例"""
from prompt_engine.knowledge.embedder import PromptEmbedder
from prompt_engine.knowledge.vector_store import PromptVectorStore
from prompt_engine.knowledge.loader import PromptEntry

__all__ = ["PromptEmbedder", "PromptVectorStore", "PromptEntry"]