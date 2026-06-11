"""Embedding 生成器 — 复用 LLM 供应商的 API"""
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
        """从配置创建（复用 openai_compat 配置）"""
        llm_cfg = config.get("llm", {})
        provider = llm_cfg.get("provider", "openai_compat")
        prov_cfg = llm_cfg.get(provider, {})
        api_key = prov_cfg.get("api_key", "")
        base_url = prov_cfg.get("base_url", "https://api.openai.com/v1")
        # embedding 模型配置，没有则使用默认
        emb_cfg = config.get("knowledge", {}).get("embedding", {})
        model = emb_cfg.get("model", "text-embedding-3-small")
        return cls(api_key=api_key, base_url=base_url, model=model)