"""Optimizer — 核心编排器（支持 RAG few-shot 注入）"""
import time
from pathlib import Path
from typing import Optional
from prompt_engine.models import OptimizeRequest, OptimizeResult
from prompt_engine.config import load_config
from prompt_engine.strategies import get_strategy
from prompt_engine.llm.base import BaseLLMProvider


class Optimizer:
    """提示词优化引擎核心类"""

    def __init__(self, config: Optional[dict] = None):
        self.config = config or load_config()
        self._provider = BaseLLMProvider.from_config(self.config)
        self._embedder = None
        self._vector_store = None
        self._init_knowledge()

    def _init_knowledge(self):
        """初始化 RAG 知识库（如果启用）"""
        kb_cfg = self.config.get("knowledge", {})
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

    def _retrieve_few_shot(self, request: OptimizeRequest) -> str:
        """检索相似 prompt 作为 few-shot 示例"""
        if not self._vector_store:
            return ""

        query = f"{request.style.value + ' ' if request.style else ''}{request.prompt}"
        kb_cfg = self.config.get("knowledge", {}).get("retrieval", {})
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
        except Exception:
            return ""

    def _call_llm(
        self, system_prompt: str, user_prompt: str, variant: int = 0
    ) -> tuple[str, int]:
        """调用 LLM，支持多版本多样性"""
        system = system_prompt
        if variant > 0:
            system += f"\n\nIMPORTANT: This is variant {variant + 1}. Generate a DIFFERENT version from a different creative angle or perspective. Do NOT repeat the same structure as previous versions."

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_prompt},
        ]
        return self._provider.chat(messages)

    def optimize(self, request: OptimizeRequest) -> OptimizeResult:
        """单条提示词优化主流程"""
        start_time = time.time()
        try:
            # 1. 加载平台策略
            strategy_cls = get_strategy(request.platform.value)
            if not strategy_cls:
                strategy_cls = get_strategy("generic")

            # 2. 构建系统提示词
            system_prompt = strategy_cls.build_system_prompt(
                style=request.style,
                creative_level=request.creative_level,
                max_length=request.max_length,
                negative_prompt=request.negative_prompt,
            )

            # 3. RAG few-shot 注入
            few_shot = self._retrieve_few_shot(request)
            if few_shot:
                system_prompt += few_shot

            # 4. 调用 LLM（单版本或多候选）
            num = request.num_candidates
            total_tokens = 0
            candidates = []

            for i in range(num):
                raw_output, tokens = self._call_llm(system_prompt, request.prompt, variant=i)
                optimized = strategy_cls.post_process(raw_output)
                if len(optimized) > request.max_length:
                    optimized = optimized[:request.max_length]
                candidates.append(optimized)
                total_tokens += tokens

            elapsed = (time.time() - start_time) * 1000

            return OptimizeResult(
                optimized_prompt=candidates[0],
                platform=request.platform,
                style=request.style,
                model_used=self._provider.model_name,
                tokens_used=total_tokens,
                duration_ms=round(elapsed, 1),
                candidates=candidates if num > 1 else [],
            )
        except Exception as e:
            elapsed = (time.time() - start_time) * 1000
            return OptimizeResult(
                optimized_prompt=request.prompt,
                platform=request.platform,
                style=request.style,
                model_used=self._provider.model_name,
                tokens_used=0,
                duration_ms=round(elapsed, 1),
                error=str(e),
            )