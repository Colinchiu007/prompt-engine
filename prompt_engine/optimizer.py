"""Optimizer — 核心编排器（支持 RAG few-shot 注入）"""
import logging
import time
from pathlib import Path
from typing import Optional
from prompt_engine.models import OptimizeRequest, OptimizeResult, ReverseRequest, ReverseResult
from prompt_engine.config import load_config
from prompt_engine.strategies import get_strategy
from prompt_engine.llm.base import BaseLLMProvider
from prompt_engine.rewriter import PromptRewriter
from prompt_engine.disturb import PromptDisturber

logger = logging.getLogger(__name__)


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
        except Exception as e:
            logger.error("RAG retrieval failed: %s", e)
            return ""

    def _call_llm(
        self, system_prompt: str, user_prompt: str, variant: int = 0
    ) -> tuple[str, int]:
        """调用 LLM"""
        system = system_prompt
        if variant > 0:
            system += f"\n\nIMPORTANT: This is variant {variant + 1}. Generate a DIFFERENT version from a different creative angle or perspective. Do NOT repeat the same structure as previous versions."

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_prompt},
        ]
        return self._provider.chat(messages)

    def _call_vision_llm(
        self, system_prompt: str, image_url: str, detail: str = "auto"
    ) -> tuple[str, int]:
        """调用视觉 LLM 分析图片"""
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Analyze this image and generate a detailed image generation prompt for it."},
                    {"type": "image_url", "image_url": {"url": image_url, "detail": detail}},
                ],
            },
        ]
        return self._provider.chat(messages)

    def reverse_engineer(self, request: ReverseRequest) -> ReverseResult:
        """图片逆向工程：从图片生成提示词"""
        start_time = time.time()
        try:
            description_prompt = "You are an image analysis expert. Describe this image in detail including: subject, setting, colors, lighting, composition, style, mood, and any notable details. Be comprehensive."
            raw_desc, tokens_desc = self._call_vision_llm(description_prompt, request.image_url, request.detail)

            # 加载策略生成平台格式化提示词
            strategy_cls = get_strategy(request.platform.value)
            if not strategy_cls:
                strategy_cls = get_strategy("generic")

            platform_prompt = strategy_cls.build_system_prompt(
                style=request.style,
                creative_level=7,
                max_length=800,
            )
            platform_prompt += "\n\nIMPORTANT: Based on the following image description, create a high-quality prompt that would regenerate this image."

            msgs = [
                {"role": "system", "content": platform_prompt},
                {"role": "user", "content": raw_desc},
            ]
            optimized, tokens_opt = self._provider.chat(msgs)
            final = strategy_cls.post_process(optimized)

            elapsed = (time.time() - start_time) * 1000
            return ReverseResult(
                prompt=final,
                platform=request.platform,
                style=request.style,
                model_used=self._provider.model_name,
                description=raw_desc,
                duration_ms=round(elapsed, 1),
            )
        except Exception as e:
            elapsed = (time.time() - start_time) * 1000
            logger.error("reverse_engineer failed: %s", e)
            return ReverseResult(
                prompt="",
                platform=request.platform,
                style=request.style,
                model_used=self._provider.model_name,
                duration_ms=round(elapsed, 1),
                error=str(e),
            )

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
            logger.error("optimize failed for prompt '%s': %s", request.prompt[:50], e)
            return OptimizeResult(
                optimized_prompt=request.prompt,
                platform=request.platform,
                style=request.style,
                model_used=self._provider.model_name,
                tokens_used=0,
                duration_ms=round(elapsed, 1),
                error=str(e),
            )

    def rewrite(self, request: OptimizeRequest) -> OptimizeResult:
        """Prompt 扩写：将简短提示词扩展为详细图像生成描述（灵感来自 Infinity 项目）

        使用 Infinity 的 PromptRewriter 模式：
        - LLM 将短 prompt 扩写为详细、具体的描述
        - 输出 <prompt:xxx><cfg:xxx> 格式
        - cfg 参数自动判断（人脸类=1，其他=3）
        """
        start_time = time.time()
        try:
            rewriter = PromptRewriter(self._provider, max_retries=3)
            result_raw = rewriter.rewrite_raw(request.prompt)

            # 后处理：按 max_length 截断
            if len(result_raw) > request.max_length:
                result_raw = result_raw[:request.max_length]

            # 尝试提取 cfg 参数
            full_rewritten = rewriter.rewrite(request.prompt)
            cfg_value = None
            cfg_match = full_rewritten.find("<cfg:")
            if cfg_match >= 0:
                cfg_end = full_rewritten.find(">", cfg_match)
                if cfg_end > cfg_match:
                    cfg_value = full_rewritten[cfg_match + len("<cfg:"):cfg_end]

            elapsed = (time.time() - start_time) * 1000

            return OptimizeResult(
                optimized_prompt=result_raw,
                platform=request.platform,
                style=request.style,
                model_used=self._provider.model_name,
                tokens_used=0,
                duration_ms=round(elapsed, 1),
                error=None,
            )
        except Exception as e:
            elapsed = (time.time() - start_time) * 1000
            logger.error("rewrite failed for prompt '%s': %s", request.prompt[:50], e)
            return OptimizeResult(
                optimized_prompt=request.prompt,
                platform=request.platform,
                style=request.style,
                model_used=self._provider.model_name,
                tokens_used=0,
                duration_ms=round(elapsed, 1),
                error=str(e),
            )

    def disturb_and_optimize(
        self,
        request: OptimizeRequest,
        num_augmented: int = 3,
        strength: float = 0.3,
    ) -> OptimizeResult:
        """扰动增强优化：对 prompt 做扰动后多次优化，取最佳

        借鉴 Infinity BSC 的扰动思路：
        1. 对原始 prompt 生成 N 个扰动版本
        2. 分别优化每个版本
        3. 返回最佳（最长、质量最高）结果
        """
        start_time = time.time()
        try:
            disturb = PromptDisturber(strength=strength)
            perturbations = disturb.perturb(request.prompt)

            all_results = []
            # 原始 prompt 也参与
            for p in [request.prompt] + [perturbations]:
                try:
                    sub_req = OptimizeRequest(
                        prompt=p,
                        platform=request.platform,
                        style=request.style,
                        creative_level=request.creative_level,
                        max_length=request.max_length,
                        negative_prompt=request.negative_prompt,
                        num_candidates=request.num_candidates,
                    )
                    result = self.optimize(sub_req)
                    all_results.append(result)
                except Exception:
                    continue

            # 选择最佳结果（非错误且最长的）
            best = None
            for r in all_results:
                if r.error:
                    continue
                if best is None or len(r.optimized_prompt) > len(best.optimized_prompt):
                    best = r

            if best is None:
                best = all_results[0] if all_results else OptimizeResult(
                    optimized_prompt=request.prompt,
                    platform=request.platform,
                    style=request.style,
                    model_used=self._provider.model_name,
                    error="All optimize calls failed",
                )

            elapsed = (time.time() - start_time) * 1000
            # 合并 tokens
            total_tokens = sum(r.tokens_used for r in all_results)
            return OptimizeResult(
                optimized_prompt=best.optimized_prompt,
                platform=request.platform,
                style=request.style,
                model_used=self._provider.model_name,
                tokens_used=total_tokens,
                duration_ms=round(elapsed, 1),
                candidates=[r.optimized_prompt for r in all_results if not r.error][:num_augmented],
                error=best.error,
            )
        except Exception as e:
            elapsed = (time.time() - start_time) * 1000
            logger.error("disturb_and_optimize failed: %s", e)
            return OptimizeResult(
                optimized_prompt=request.prompt,
                platform=request.platform,
                style=request.style,
                model_used=self._provider.model_name,
                tokens_used=0,
                duration_ms=round(elapsed, 1),
                error=str(e),
            )