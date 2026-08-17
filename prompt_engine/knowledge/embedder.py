"""Embedding 生成器 — 使用 knowledge.embedding 的独立配置"""
from typing import Optional
import numpy as np
from openai import OpenAI


class PromptEmbedder:
    """Embedding 生成器"""

    def __init__(self, api_key: str, base_url: str, model: str = "text-embedding-3-small"):
        self._client = OpenAI(api_key=api_key, base_url=base_url)
        self._model = model

    def embed(self, text: str) -> list[float]:
        """单条文本嵌入"""
        resp = self._client.embeddings.create(input=text, model=self._model)
        return resp.data[0].embedding

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """批量嵌入"""
        resp = self._client.embeddings.create(input=texts, model=self._model)
        return [d.embedding for d in resp.data]

    @classmethod
    def from_config(cls, config: dict) -> "PromptEmbedder":
        """从 knowledge.embedding 独立配置创建。"""
        emb_cfg = config.get("knowledge", {}).get("embedding", {})
        if not isinstance(emb_cfg, dict):
            raise ValueError("knowledge.embedding 必须是对象")
        api_key = emb_cfg.get("api_key", "")
        if not isinstance(api_key, str) or not api_key.strip():
            raise ValueError("knowledge.embedding.api_key 必填")
        base_url = emb_cfg.get("base_url", "https://api.openai.com/v1")
        if not isinstance(base_url, str) or not base_url.strip():
            raise ValueError("knowledge.embedding.base_url 必须是非空字符串")
        model = emb_cfg.get("model", "text-embedding-3-small")
        return cls(api_key=api_key.strip(), base_url=base_url.strip(), model=model)
