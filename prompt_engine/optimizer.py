"""Optimizer — 核心编排器（支持 RAG few-shot 注入）"""
import logging
import time
from pathlib import Path
from typing import Optional
from prompt_engine.models import OptimizeRequest, OptimizeResult, ReverseRequest, ReverseResult, StyleCategory, StyleType
from prompt_engine.config import load_config
from prompt_engine.strategies import get_strategy
from prompt_engine.llm.base import BaseLLMProvider
from prompt_engine.rewriter import PromptRewriter
from prompt_engine.disturb import PromptDisturber
from prompt_engine.classifier import StyleCategoryClassifier
from prompt_engine.cache import SqlitePromptCache, MemoryPromptCache

logger = logging.getLogger(__name__)

# ── 内存缓存池（L1 热点缓存）
_PromptCacheKey = tuple[str, str, int, int, str, int]
_PromptCache: dict[_PromptCacheKey, OptimizeResult] = {}

# ── TF-IDF 向量化器（惰性初始化）
_VECTORIZER = None

def _get_vectorizer():
    global _VECTORIZER
    if _VECTORIZER is None:
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            import numpy as np
            _VECTORIZER = TfidfVectorizer(analyzer='char', ngram_range=(2, 3))
        except ImportError:
            _VECTORIZER = False  # sentinel
    return _VECTORIZER if _VECTORIZER is not False else None

def _legacy_similarity(a: str, b: str) -> float:
    """旧版相似度（set inclusion），作为 TF-IDF 的降级"""
    a = a.strip().lower()
    b = b.strip().lower()
    if a == b:
        return 1.0
    a_words = set(a.split())
    b_words = set(b.split())
    if a_words & b_words:
        return 0.8
    return 0.5

def _similarity(a: str, b: str) -> float:
    """TF-IDF 余弦相似度（降级到旧算法）"""
    # 精确匹配快速路径
    if a.strip().lower() == b.strip().lower():
        return 1.0

    vec = _get_vectorizer()
    if vec is None:
        return _legacy_similarity(a, b)

    try:
        import numpy as np
        tfidf = vec.fit_transform([a.strip().lower(), b.strip().lower()])
        sim = (tfidf * tfidf.T).A[0, 1]
        return float(sim)
    except Exception:
        return _legacy_similarity(a, b)

def fuzzy_match_prompt(prompt: str, platform: str, creative_level: int = 7, max_length: int = 500, negative_prompt: str = "", num_candidates: int = 1, similarity_threshold: float = 0.7) -> Optional[OptimizeResult]:
    """模糊匹配相似 prompt，命中缓存后返回"""

    normalized = prompt.strip().lower()
    best_result = None
    best_score = 0.0
    
    for (cached_p, cached_plat, cached_cl, cached_ml, cached_np, cached_nc), cached_res in _PromptCache.items():
        if cached_plat != platform:
            continue
        
        # 匹配（prompt + 配置参数必须完全一致）
        if cached_cl != creative_level or cached_ml != max_length or cached_np != negative_prompt or cached_nc != num_candidates:
            continue
        score = _similarity(normalized, cached_p.lower())
        if score > best_score:
            best_score = score
            best_result = cached_res
    
    if best_score >= similarity_threshold:
        logger.info("Cache hit: %s @ %s (similarity: %.3f)", normalized, platform, best_score)
        return best_result
    
    return None




# StyleCategory → StyleType 自动映射
# 当自动检测到某些 MJ 风格类别时，映射到平台可用的 StyleType
_STYLE_CATEGORY_TO_TYPE: dict[StyleCategory, StyleType] = {
    StyleCategory.DRAWING_AND_ART_MEDIUMS: None,  # 由具体媒介词汇决定
    StyleCategory.THEMES: None,  # 由具体主题词汇决定
}
# 反向映射：关键词 → StyleType
_STYLE_TYPE_KEYWORDS: dict[StyleType, list[str]] = {
    # 具体媒介排前面（更高优先级）
    StyleType.WATERCOLOR: ["watercolor", "water colour", "water-colour",
                           "水彩", "水彩画"],
    StyleType.OIL_PAINTING: ["oil painting", "oil paint",
                             "油画"],
    StyleType.PIXEL: ["pixel art", "8-bit", "retro game", "pixel",
                      "像素", "像素画", "点阵"],
    StyleType.ANIME: ["anime", "manga", "cel shaded", "cell shade", "japanese animation",
                      "动漫", "动画", "二次元"],
    StyleType.CARTOON: ["cartoon", "comic", "toon",
                        "卡通", "漫画风格", "美式卡通"],
    # 设计风格
    StyleType.CYBERPUNK: ["cyberpunk", "neon", "dystopian", "cyber",
                          "赛博朋克", "赛博", "霓虹"],
    StyleType.MINIMALIST: ["minimalist", "minimal", "clean", "simple",
                           "极简", "简约", "极简主义"],
    StyleType.FANTASY: ["fantasy", "magical", "mythical", "medieval", "dragon", "elf",
                        "奇幻", "魔法", "神话"],
    StyleType.ABSTRACT: ["abstract", "abstract art",
                         "抽象", "抽象画"],
    # 摄影与写实
    StyleType.PHOTOGRAPHY: ["photography", "photo", "camera", "lens", "photograph", "portrait", "shot on",
                            "摄影", "相机", "镜头", "照片"],
    StyleType.PORTRAIT: ["portrait", "headshot", "close-up", "face",
                         "人像", "肖像", "特写"],
    StyleType.REALISTIC: ["realistic", "photorealistic", "realism", "hyperrealistic",
                          "写实", "逼真"],
    # 技术类
    StyleType._3D_RENDER: ["3d render", "cgi", "pbr", "render", "3d model", "vray",
                           "3D渲染", "渲染", "三维"],
    StyleType.LANDSCAPE: ["landscape", "mountain", "sea", "ocean", "nature", "scenery", "vista",
                          "风景", "山水", "自然", "景观", "风光"],
}


def _detect_style_type_from_category(
    category_result: "StyleCategoryResult",  # noqa: F821
    prompt: str,
) -> tuple[Optional[StyleType], Optional["StyleCategoryResult"]]:  # noqa: F821
    """从 MJ 风格分类结果自动推断 StyleType。

    1. 优先匹配 StyleType 关键词
    2. 如果没匹配到，回退到 StyleCategory → StyleType 映射
    """
    prompt_lower = prompt.lower()

    # 第一轮：关键词匹配 StyleType
    for st, keywords in _STYLE_TYPE_KEYWORDS.items():
        for kw in keywords:
            if kw in prompt_lower:
                return st, category_result

    # 第二轮：StyleCategory 映射
    if category_result and category_result.categories:
        # 媒体类别直接映射
        if StyleCategory.DRAWING_AND_ART_MEDIUMS in category_result.categories:
            # 从 prompt 中找具体绘画媒介
            if any(kw in prompt_lower for kw in ["watercolor", "water colour", "水彩"]):
                return StyleType.WATERCOLOR, category_result
            if any(kw in prompt_lower for kw in ["oil painting", "oil paint", "油画"]):
                return StyleType.OIL_PAINTING, category_result
            if any(kw in prompt_lower for kw in ["pixel art", "pixel", "像素"]):
                return StyleType.PIXEL, category_result

        if StyleCategory.DIGITAL in category_result.categories:
            if any(kw in prompt_lower for kw in ["pixel", "retro game", "8-bit"]):
                return StyleType.PIXEL, category_result
            return StyleType._3D_RENDER, category_result

        if StyleCategory.CAMERA in category_result.categories:
            return StyleType.PHOTOGRAPHY, category_result

        if StyleCategory.NATURE_AND_ANIMALS in category_result.categories:
            if any(kw in prompt_lower for kw in ["portrait", "close-up", "face", "人像", "肖像"]):
                return StyleType.PORTRAIT, category_result
            return StyleType.LANDSCAPE, category_result

    return None, category_result


def _style_category_to_db_key(cat: StyleCategory) -> str:
    """将 StyleCategory 枚举值转换为 MJ 数据库的 key（硬编码映射，保证 100% 准确）。"""
    _CATEGORY_DB_MAP = {
        StyleCategory.LIGHTING: "Lighting",
        StyleCategory.MATERIAL_PROPERTIES: "Material_Properties",
        StyleCategory.MATERIALS: "Materials",
        StyleCategory.DIMENSIONALITY: "Dimensionality",
        StyleCategory.COLORS_AND_PALETTES: "Colors_and_Palettes",
        StyleCategory.COMBINATIONS: "Combinations",
        StyleCategory.CAMERA: "Camera",
        StyleCategory.PERSPECTIVE: "Perspective",
        StyleCategory.STRUCTURAL_MODIFICATION: "Structural_Modification",
        StyleCategory.NATURE_AND_ANIMALS: "Nature_and_Animals",
        StyleCategory.OBJECTS: "Objects",
        StyleCategory.OUTER_SPACE: "Outer_Space",
        StyleCategory.GEOMETRY: "Geometry",
        StyleCategory.GEOGRAPHY_AND_CULTURE: "Geography_and_Culture",
        StyleCategory.DRAWING_AND_ART_MEDIUMS: "Drawing_and_Art_Mediums",
        StyleCategory.SFX_AND_SHADERS: "SFX_and_Shaders",
        StyleCategory.THEMES: "Themes",
        StyleCategory.INTANGIBLES: "Intangibles",
        StyleCategory.TV_AND_MOVIES: "TV_and_Movies",
        StyleCategory.SONG_LYRICS: "Song_Lyrics",
        StyleCategory.DESIGN_STYLES: "Design_Styles",
        StyleCategory.DIGITAL: "Digital",
        StyleCategory.EXPERIMENTAL: "Experimental",
        StyleCategory.EMOJIS: "Emojis",
        StyleCategory.MISCELLANEOUS: "Miscellaneous",
    }
    return _CATEGORY_DB_MAP.get(cat, cat.value.replace("_", " ").title().replace(" ", "_"))


def _get_preferred_db_keys(category_result: Optional["StyleCategoryResult"]) -> list[str]:  # noqa: F821
    """从分类结果中提取 MJ DB 可用的 key 列表。"""
    if not category_result or not category_result.categories:
        return []
    return [_style_category_to_db_key(cat) for cat in category_result.categories]


class Optimizer:
    """提示词优化引擎核心类"""

    def __init__(self, config: Optional[dict] = None):
        self.config = config or load_config()
        self._provider = BaseLLMProvider.from_config(self.config)
        self._embedder = None
        self._vector_store = None
        self._cat_classifier = StyleCategoryClassifier()
        self._init_knowledge()
        # ── 双级缓存 ──
        self._sqlite_cache = SqlitePromptCache()
        self._mem_cache = MemoryPromptCache()

    def _cache_key(self, prompt: str, platform: str, creative_level: int,
                   max_length: int, negative_prompt: str, num_candidates: int) -> str:
        return SqlitePromptCache.make_key(prompt, platform, creative_level, max_length, negative_prompt, num_candidates)

    def _cache_get(self, prompt: str, platform: str, creative_level: int,
                   max_length: int, negative_prompt: str, num_candidates: int) -> Optional[OptimizeResult]:
        """双级缓存读取：L1 内存 → L2 SQLite（预热 L1）"""
        key = self._cache_key(prompt, platform, creative_level, max_length, negative_prompt, num_candidates)
        # L1
        cached = self._mem_cache.get(key)
        if cached:
            return cached
        # L2
        cached = self._sqlite_cache.get(prompt, platform, creative_level, max_length, negative_prompt, num_candidates)
        if cached:
            self._mem_cache.set(key, cached)  # 预热 L1
            return cached
        return None

    def _cache_set(self, prompt: str, platform: str, creative_level: int,
                   max_length: int, negative_prompt: str, num_candidates: int,
                   result: OptimizeResult):
        """写入双级缓存"""
        key = self._cache_key(prompt, platform, creative_level, max_length, negative_prompt, num_candidates)
        self._mem_cache.set(key, result)
        self._sqlite_cache.set(prompt, platform, creative_level, max_length, negative_prompt, num_candidates, result)
        # 同时写入旧版 dict 缓存（兼容 fuzzy_match_prompt）
        _PromptCache[(prompt.strip().lower(), platform, creative_level, max_length, negative_prompt, num_candidates)] = result

    @staticmethod
    def _render_from_template(request: OptimizeRequest) -> OptimizeResult:
        """低创意等级（≤3）用模板直出，不调 LLM"""
        from prompt_engine.template_engine import PromptBlock

        strategy_cls = get_strategy(request.platform.value)
        if not strategy_cls:
            strategy_cls = get_strategy("generic")

        cl = max(1, min(3, request.creative_level))

        # 基础块：用户 prompt 就是主体
        parts = [request.prompt]

        # Level 2+: 质量标签
        if cl >= 2:
            quality_tags = ["simple", "clean", "medium", "detailed", "refined"]
            parts.append(quality_tags[min(cl - 1, len(quality_tags) - 1)])

        # Level 3: 简单光影描述
        if cl >= 3:
            from random import choice
            lighting = choice(["soft lighting", "natural light", "warm glow", "bright daylight"])
            parts.append(lighting)

        raw = ", ".join(parts)
        final = strategy_cls.post_process(raw, creative_level=cl)

        return OptimizeResult(
            optimized_prompt=final,
            platform=request.platform,
            style=request.style,
            model_used="template",
            tokens_used=0,
            duration_ms=0,
            error=None,
        )

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
            final = strategy_cls.post_process(optimized, creative_level=7)

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
            # ✨ 双级缓存检查（SQLite + 内存）
            from prompt_engine.models import OptimizeResult as _OptRes
            cached = self._cache_get(
                request.prompt, request.platform.value,
                request.creative_level, request.max_length,
                request.negative_prompt or "", request.num_candidates
            )
            if cached:
                logger.info("Cache hit: %s @ %s", request.prompt[:50], request.platform.value)
                return cached

            # ✨ F2: 低创意模板直出（免 LLM）
            if request.creative_level <= 3:
                logger.info("Template render: creative_level=%d, %s @ %s",
                            request.creative_level, request.prompt[:50], request.platform.value)
                return self._render_from_template(request)

            detected_result: Optional["StyleCategoryResult"] = None
            
            # 0. 自动风格检测（当 style 未指定时）
            effective_style = request.style
            if request.auto_detect_style and request.style is None:
                detected_result = self._cat_classifier.classify(
                    request.prompt, max_categories=5, use_llm=False
                )
                if detected_result and detected_result.categories:
                    detected_style, detected_result = _detect_style_type_from_category(
                        detected_result, request.prompt
                    )
                    if detected_style:
                        effective_style = detected_style
                        logger.info(
                            "Auto-detected style: %s from MJ categories: %s",
                            detected_style.value,
                            [c.value for c in detected_result.categories],
                        )

            # 1. 加载平台策略
            strategy_cls = get_strategy(request.platform.value)
            if not strategy_cls:
                strategy_cls = get_strategy("generic")

            # 2. 构建系统提示词
            system_prompt = strategy_cls.build_system_prompt(
                style=effective_style,
                creative_level=request.creative_level,
                max_length=request.max_length,
                negative_prompt=request.negative_prompt,
            )

            # 2.5 PROJECT-012 上下文注入（角色一致性）
            if request.context:
                ctx = request.context
                parts = []
                if ctx.get("setting"):
                    parts.append(f"Setting/场景: {ctx['setting']}")
                if ctx.get("character"):
                    parts.append(f"Current character/当前角色: {ctx['character'].get('name', '')}")
                if ctx.get("character_list"):
                    names = [c["name"] for c in ctx["character_list"] if "name" in c]
                    parts.append(f"All characters/全部角色: {', '.join(names)}")
                if ctx.get("synopsis"):
                    parts.append(f"Story synopsis/故事梗概: {ctx['synopsis'][:200]}")
                if parts:
                    system_prompt += "\n\n## Character consistency / 角色一致性\n"
                    system_prompt += "\n".join(parts)
                    system_prompt += "\n- Keep the same character identity (appearance/服装/发型) across all images where the same name appears."
                    system_prompt += "\n- 相同名字的角色在所有图片中保持同一身份（外貌、服装、发型一致）。"

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
                preferred_db_keys = _get_preferred_db_keys(detected_result)
                optimized = strategy_cls.post_process(
                    raw_output,
                    creative_level=request.creative_level,
                    preferred_categories=preferred_db_keys or None,
                )
                if len(optimized) > request.max_length:
                    optimized = optimized[:request.max_length]
                candidates.append(optimized)
                total_tokens += tokens

            elapsed = (time.time() - start_time) * 1000
            
            # 存入双级缓存以便下次命中
            result = _OptRes(
                optimized_prompt=candidates[0],
                platform=request.platform,
                style=effective_style if effective_style != request.style else request.style,
                model_used=self._provider.model_name,
                tokens_used=total_tokens,
                duration_ms=round(elapsed, 1),
                candidates=candidates if num > 1 else [],
                detected_categories=detected_result,
            )
            self._cache_set(
                request.prompt, request.platform.value,
                request.creative_level, request.max_length,
                request.negative_prompt or "", request.num_candidates,
                result
            )
            return result

            result = None  # Only for type checker
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