"""Bitwise + Style Category Classifier."""
import json
import logging
import math
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    import torch
    import torch.nn as nn

from prompt_engine.models import StyleCategory, StyleCategoryResult

logger = logging.getLogger(__name__)


# ================================================================
# Bitwise Classifier
# ================================================================

class BitwiseClassifier:
    """比特级分类器：将 N 分类拆解为 d 个二分类（需要 torch 可选安装）。

    注意：实验性功能，未集成到主分类管线。
    当前分类管线使用 keyword_match → vector_rag → llm_classify 三级流水线，
    无需 PyTorch。
    """
    def __init__(self, embed_dim: int, num_classes: int, hidden_dim: Optional[int] = None):
        import torch
        import torch.nn as nn
        self._torch = torch
        self._nn = nn
        
        self.num_classes = num_classes
        self.num_bits = max(1, math.ceil(math.log2(num_classes))) if num_classes > 1 else 1
        self.bit_mask = (1 << self.num_bits) - 1
        if hidden_dim is not None and hidden_dim != embed_dim:
            self.project = nn.Linear(embed_dim, hidden_dim)
            self.act = nn.GELU()
            self.dropout = nn.Dropout(0.1)
            embed_dim = hidden_dim
        self.bit_heads = nn.ModuleList([nn.Linear(embed_dim, 2) for _ in range(self.num_bits)])
        logger.info("BitwiseClassifier: %d classes -> %d bits", num_classes, self.num_bits)
    def __call__(self, x):
        return self.forward(x)
    def forward(self, x) -> "torch.Tensor":
        import torch.nn.functional as F
        torch = self._torch
        if hasattr(self, "project"):
            x = self.dropout(self.act(self.project(x)))
        return torch.stack([head(x) for head in self.bit_heads], dim=1)
    def decode(self, bit_logits) -> "torch.Tensor":
        torch = self._torch
        bit_preds = bit_logits.argmax(dim=-1)
        result = torch.zeros(bit_logits.shape[0], dtype=torch.long, device=bit_logits.device)
        for i in range(self.num_bits):
            result += bit_preds[:, i] * (1 << i)
        return result.clamp(max=self.bit_mask)
    def loss(self, bit_logits, target_classes) -> "torch.Tensor":
        import torch.nn.functional as F
        bit_targets = self._classes_to_bits(target_classes)
        return sum(F.cross_entropy(bit_logits[:, i], bit_targets[:, i])
                   for i in range(self.num_bits)) / self.num_bits
    def _classes_to_bits(self, classes) -> "torch.Tensor":
        torch = self._torch
        bits = torch.zeros(classes.shape[0], self.num_bits, dtype=torch.long, device=classes.device)
        val = classes.clamp(max=self.bit_mask)
        for i in range(self.num_bits):
            bits[:, i] = val & 1
            val >>= 1
        return bits
    @classmethod
    def from_config(cls, embed_dim: int, num_classes: int) -> "BitwiseClassifier":
        return cls(embed_dim, num_classes, hidden_dim=max(embed_dim // 2, 64))


# ================================================================
# Style Category Classifier — MJ 26 维度零样本分类
# ================================================================

# 每个 StyleCategory → MJ 数据库关键词（取前 N 个作为匹配种子）
_CATEGORY_KEYWORDS: dict[StyleCategory, set[str]] = {}

# 每个 StyleCategory → 描述性关键词（LLM 理解用）
from prompt_engine.models import CATEGORY_DESCRIPTIONS
_CATEGORY_DESCRIPTIONS: dict[StyleCategory, str] = CATEGORY_DESCRIPTIONS


def _load_category_keywords() -> dict[StyleCategory, list[str]]:
    """从 MJ 数据库加载每个类别的代表性关键词（每个类别最多 15 个）。"""
    global _CATEGORY_KEYWORDS
    if _CATEGORY_KEYWORDS:
        return _CATEGORY_KEYWORDS
    db_path = Path(__file__).parent / "data" / "mj_style_final.json"
    db: dict = {}
    if db_path.exists():
        try:
            with open(db_path, "r", encoding="utf-8") as f:
                db = json.load(f)
        except Exception as e:
            logger.debug("Non-critical error loading data: %s", e)
    # MJ 类别名 → StyleCategory 枚举映射（从 models.py 引入）
    from prompt_engine.models import DB_KEY_TO_STYLE_CATEGORY
    CAT_MAP = DB_KEY_TO_STYLE_CATEGORY
    result = {}
    for mj_key, category in CAT_MAP.items():
        kws = db.get(mj_key, [])
        # 过滤太短的（<3 字符且不含空格/连字符）
        filtered = [k for k in kws if len(k) >= 3 or " " in k or "-" in k or "\u00a0" in k]
        result[category] = filtered[:15]  # 每个类别取前 15 个
    _CATEGORY_KEYWORDS = result
    return result


def _keyword_match(prompt: str, max_score: float = 0.7) -> tuple[list[StyleCategory], dict[str, list[str]], float]:
    """关键词匹配 — 第一轮：检查 prompt 中是否包含 MJ 数据库关键词。

    使用子串匹配 + 相似度阈值，避免误匹配短词。
    返回: (categories, keywords_found, confidence)
    """
    cat_kws = _load_category_keywords()
    keywords_found: dict[str, list[str]] = {}
    scores: dict[StyleCategory, float] = {}
    
    # 将 prompt 转为小写用于匹配
    prompt_lower = prompt.lower()
    
    # 中文同义词映射：中文词 → (StyleCategory, [匹配到的关键词])
    # 每个 MJ 类别添加对应的中文同义词
    CN_SYNONYMS: dict[StyleCategory, set[str]] = {
        StyleCategory.LIGHTING: {"光照", "灯光", "光线", "光影", "辉光", "体积光", "阴影", "逆光", "侧光", "顶光", "补光", "柔光", "硬光"},
        StyleCategory.MATERIAL_PROPERTIES: {"材质", "质感", "表面", "透明度", "反射", "折射", "光泽", "磨砂", "抛光", "光滑", "粗糙"},
        StyleCategory.MATERIALS: {"材料", "金属", "塑料", "织物", "木材", "石材", "玻璃", "陶瓷", "皮革", "纸张", "布料"},
        StyleCategory.DIMENSIONALITY: {"维度", "3D", "2D", "2.5D", "立体", "空间", "深度"},
        StyleCategory.COLORS_AND_PALETTES: {"色彩", "色调", "调色板", "互补色", "类似色", "单色", "双色", "三色", "多色", "渐变"},
        StyleCategory.COMBINATIONS: {"组合", "特殊色彩", "发光", "珍珠色", "虹彩", "幻彩", "荧光"},
        StyleCategory.CAMERA: {"相机", "镜头", "摄影", "光圈", "焦距", "拍摄", "快门", "曝光", "ISO", "广角", "长焦", "微距", "鱼眼", "移轴", "移焦"},
        StyleCategory.PERSPECTIVE: {"视角", "透视", "构图", "仰视", "俯视", "鱼眼", "广角", "特写", "中景", "远景", "全景", "鸟瞰", "虫瞰"},
        StyleCategory.STRUCTURAL_MODIFICATION: {"变形", "螺旋", "扭曲", "抽象", "分形", "莫尔", "视错觉"},
        StyleCategory.NATURE_AND_ANIMALS: {"自然", "动物", "植物", "风景", "山水", "花卉", "森林", "海洋", "沙漠", "雪山", "草原", "野外", "golden", "dog", "retriever", "wildflower", "meadow", "flower", "tree", "bird", "rabbit", "cat", "horse", "fish", "insect", "butterfly", "sunset", "dawn", "sunrise", "twilight", "nature", "animal", "plant", "wildlife", "wild", "landscape"},
        StyleCategory.OBJECTS: {"物体", "道具", "日常", "机械", "电子", "建筑", "家具", "汽车", "飞机", "船只", "武器", "饰品"},
        StyleCategory.OUTER_SPACE: {"太空", "星空", "星球", "宇宙", "星际", "银河", "黑洞", "彗星", "陨石", "卫星", "星云", "极光"},
        StyleCategory.GEOMETRY: {"几何", "图案", "对称", "多面体", "网格", "分形", "数学", "伊斯兰", "曼陀罗", "六边形", "三角形"},
        StyleCategory.GEOGRAPHY_AND_CULTURE: {"文化", "地域", "民族", "历史", "建筑", "传统", "中国", "日本", "欧洲", "美洲", "非洲", "中东", "印度", "希腊", "罗马", "埃及", "北欧", "东南亚"},
        StyleCategory.DRAWING_AND_ART_MEDIUMS: {"绘画", "水彩", "油画", "素描", "版画", "墨", "彩铅", "蜡笔", "粉彩", "丙烯", "坦培拉", "壁画", "装饰艺术", "浮世绘", "工笔画", "写意"},
        StyleCategory.SFX_AND_SHADERS: {"特效", "着色器", "光效", "粒子", "后期", "景深", "光晕", "镜头光斑", "色差", "运动模糊", "光线追踪", "全局光照", "体积雾", "焦散", "折射"},
        StyleCategory.THEMES: {"主题", "氛围", "情绪", "概念", "美学", "亚文化", "蒸汽波", "废土", "末日", "田园", "浪漫", "恐怖", "神秘", "史诗", "戏剧", "抒情", "极简", "繁复", "装饰", "抽象"},
        StyleCategory.INTANGIBLES: {"能量", "量子", "电磁", "不可见", "无形", "意识", "幻觉", "梦境", "潜意识", "精神", "灵魂", "意识流"},
        StyleCategory.TV_AND_MOVIES: {"影视", "电影", "电视剧", "动画", "漫画", "剧集", "卡通", "真人", "纪录片", "科幻", "奇幻", "动作", "剧情", "恐怖", "喜剧"},
        StyleCategory.SONG_LYRICS: {"歌词", "音乐", "旋律", "节奏", "和声", "编曲", "乐器", "声乐", "说唱", "摇滚", "电子", "古典", "爵士", "流行", "民谣", "嘻哈", "氛围", "后摇", "梦幻"},
        StyleCategory.DESIGN_STYLES: {"设计风格", "艺术", "运动", "装饰", "极简", "波普", "包豪斯", "装饰艺术", "新艺术", "超现实主义", "立体主义", "印象派", "表现主义", "抽象表现主义", "极简主义", "功能主义", "粗野主义", "高技派", "数字艺术", "新媒体艺术", "概念艺术", "装置艺术", "cyberpunk", "steampunk", "gothic", "baroque", "rococo", "renaissance", "art deco", "pop art", "minimalism", "futurism", "surrealism", "cubism", "impressionism", "expressionism", "bauhaus", "deco", "modern", "postmodern", "retro", "vintage", "classic"},
        StyleCategory.DIGITAL: {"数字艺术", "像素", "电子游戏", "CGI", "3D渲染", "建模", "纹理", "贴图", "光影", "烘焙", "实时", "离线", "光线追踪", "体素", "低多边形", "等距", "平台", "RPG", "冒险", "射击"},
        StyleCategory.EXPERIMENTAL: {"实验", "前卫", "概念艺术", "非常规", "反传统", "后现代", "达达主义", "超现实主义", "观念艺术"},
        StyleCategory.EMOJIS: {"emoji", "表情", "符号", "unicode", "象形", "图标"},
        StyleCategory.MISCELLANEOUS: {"杂项", "特殊", "其他", "渲染", "输出", "成品", "最终", "商业", "广告", "印刷", "海报", "包装", "品牌", "logo"},
    }
    
    # 第一步：中文同义词匹配（快速，覆盖中文 prompt）
    cn_matched_categories: set[StyleCategory] = set()
    for category, synonyms in CN_SYNONYMS.items():
        matched = [syn for syn in synonyms if syn in prompt_lower]
        if matched:
            cn_matched_categories.add(category)
            scores[category] = scores.get(category, 0.0) + len(matched) * 0.9
    
    # 第二步：英文关键词匹配（使用单词边界匹配，避免子串误匹配）
    for category, kws in cat_kws.items():
        if category in (StyleCategory.SONG_LYRICS, StyleCategory.EXPERIMENTAL, StyleCategory.EMOJIS, StyleCategory.TV_AND_MOVIES):
            continue
        for kw in kws[:30]:
            kw_lower = kw.lower()
            kw_parts = kw_lower.split()
            if not kw_parts:
                continue
            matching_parts = sum(1 for p in kw_parts if p in prompt_lower)
            if matching_parts >= len(kw_parts) * 0.5:
                # 权重因子：用户反馈驱动的关键词权重
                weight = _get_weights().get(category.value, {}).get(kw_lower, 1.0)
                scores[category] = scores.get(category, 0.0) + 0.8 * (matching_parts / max(len(kw_parts), 1)) * weight

    # 第三步：使用 CN_SYNONYMS 中的英文词进行补充匹配（cyberpunk, steampunk, gothic 等）
    for category, syns in CN_SYNONYMS.items():
        for syn in syns:
            syn_lower = syn.lower()
            if len(syn_lower) >= 3 and syn_lower in prompt_lower:
                scores[category] = scores.get(category, 0.0) + 0.5

    # 合并结果
    if scores:
        max_score_val = max(scores.values())
        if max_score_val > 0:
            normalized = {k: v / max_score_val for k, v in scores.items()}
            categories = [k for k, v in normalized.items() if v >= max_score * 0.3]
            conf = max(normalized.values())
            
            # 收集每个类别匹配的关键词（要求 70% 的子单词匹配）
            for cat in categories:
                matched_kws = []
                for kw in cat_kws.get(cat, []):
                    kw_parts = kw.lower().split()
                    matching_parts = sum(1 for p in kw_parts if p in prompt_lower)
                    if matching_parts >= len(kw_parts) * 0.7:
                        matched_kws.append(kw)
                        if len(matched_kws) >= 5:
                            break
                keywords_found[cat.value] = list(set(matched_kws))[:5]
            return categories, keywords_found, conf
    
    return [], keywords_found, 0.0


def _build_llm_prompt(prompt: str, categories: list[StyleCategory]) -> tuple[str, str]:
    """构建 LLM 分类的 prompt 和 system prompt。"""
    cat_list = "\n".join(
        f"- {c.value}: {_CATEGORY_DESCRIPTIONS.get(c, '')}"
        for c in categories
    )
    system = f"""你是一个风格分类专家。将用户的描述分配到 MJ Style Reference 的 26 个风格维度中。

{cat_list}

规则：
1. 一个描述可能对应多个维度（例如 "油画风格的星空" → painting_mediums + outer_space）
2. 输出 JSON 格式：{{"categories": ["cat1", "cat2", ...], "reason": "简要说明"}}
3. 如果描述中没有明显的风格倾向，返回空列表
4. 只输出 JSON，不要其他内容"""
    
    user = f"请分析以下描述的 MJ 风格分类：\n\n{prompt}"
    return system, user


class StyleCategoryClassifier:
    """MJ 26 维度风格分类器 — 关键词匹配 + 向量语义搜索 + LLM 零样本分类。

    三级流水线：
    1. 关键词匹配（快速，~0ms）— 中文+英文同义词，精确命中
    2. 向量语义搜索（~50ms）— TF-IDF 余弦相似度，模糊匹配
    3. LLM 零样本分类（~1s）— 语义理解，兜底

    不依赖 PyTorch/训练数据，零样本工作。
    """

    def __init__(self, llm_chat_func=None):
        """初始化分类器。

        Args:
            llm_chat_func: 可选的 LLM 聊天函数，签名 (system: str, user: str) -> str
                           如果不提供，关键词匹配 + 向量搜索后仍未找到则返回空结果
        """
        self._llm_chat = llm_chat_func

    def classify(
        self,
        prompt: str,
        max_categories: int = 5,
        use_llm: bool = True,
    ) -> StyleCategoryResult:
        """对 prompt 进行风格分类。

        三级流水线：
        1. 关键词匹配（精确命中）
        2. 向量语义搜索（TF-IDF 模糊匹配，增强中文+英文泛化）
        3. LLM 零样本分类（兜底，需提供 llm_chat_func）

        Args:
            prompt: 原始 prompt 文本
            max_categories: 最多返回几个类别
            use_llm: 是否使用 LLM 做深度分类（当关键词+向量搜索得分低时）

        Returns:
            StyleCategoryResult 分类结果
        """
        # 第一步：关键词匹配
        keywords_found: dict[str, list[str]] = {}
        categories, kw_found, confidence = _keyword_match(prompt)
        keywords_found.update(kw_found)

        # 如果关键词匹配已有结果且置信度高，直接返回
        if categories and confidence >= 0.6:
            categories = sorted(categories, key=lambda c: 1.0, reverse=True)
            result = StyleCategoryResult(
                categories=categories[:max_categories],
                keywords_found=keywords_found,
                method="keyword_match",
                confidence=confidence,
            )
            logger.debug("Keyword match: %d categories, confidence=%.2f",
                        len(result.categories), confidence)
            return result

        # 第二步：向量语义搜索（关键词匹配得分低时启用）
        if not categories or confidence < 0.6:
            try:
                rag_scores = self._vector_search(prompt)
                if rag_scores:
                    # 构建 StyleCategory → score 映射
                    cat_scores: dict[StyleCategory, float] = {}
                    for cat in StyleCategory:
                        db_key = _style_cat_to_db_key(cat)
                        if db_key in rag_scores:
                            cat_scores[cat] = rag_scores[db_key]

                    if cat_scores:
                        # 与关键词匹配结果合并（加权）
                        kw_conf = confidence if categories else 0.0
                        for cat in cat_scores:
                            if cat in cat_scores:
                                cat_scores[cat] = max(cat_scores[cat], kw_conf * 0.3)

                        # 按得分排序
                        sorted_cats = sorted(
                            cat_scores.keys(),
                            key=lambda c: cat_scores[c],
                            reverse=True,
                        )[:max_categories]

                        # 如果向量搜索得分比关键词高，用向量搜索方法
                        max_rag = max(cat_scores.values()) if cat_scores else 0
                        method = "keyword_match" if categories and confidence >= max_rag else "vector_rag"
                        rag_conf = max_rag

                        result = StyleCategoryResult(
                            categories=sorted_cats,
                            keywords_found=keywords_found,
                            method=method,
                            confidence=rag_conf,
                        )
                        logger.info("RAG vector search: %d categories, confidence=%.2f, method=%s",
                                   len(result.categories), rag_conf, method)
                        return result
            except Exception as e:
                logger.debug("Vector search failed: %s", e)

        # 第三步：LLM 分类（兜底）
        if use_llm and self._llm_chat:
            try:
                all_categories = list(StyleCategory)
                system, user = _build_llm_prompt(prompt, all_categories)
                llm_response = self._llm_chat(system, user)
                parsed_cats = self._parse_llm_response(llm_response)
                
                if parsed_cats:
                    result = StyleCategoryResult(
                        categories=parsed_cats[:max_categories],
                        keywords_found=keywords_found,
                        method="llm_classify",
                        confidence=0.6,  # LLM 零样本默认置信度
                    )
                    logger.info("LLM classify: %d categories from %s",
                               len(result.categories), result.categories)
                    return result
            except Exception as e:
                logger.warning("LLM classify failed: %s", e)
        
        # 都没找到
        return StyleCategoryResult(
            categories=[],
            keywords_found=keywords_found,
            method="keyword_match" if categories else "llm_classify",
            confidence=0.0,
        )
    
    @staticmethod
    def _parse_llm_response(response: str) -> list[StyleCategory]:
        """从 LLM 响应中解析分类结果。"""
        import json
        try:
            # 尝试找到 JSON 块
            import re
            json_match = re.search(r'\{[^{}]*"categories"[^{}]*\}', response)
            if json_match:
                data = json.loads(json_match.group())
                cat_names = data.get("categories", [])
                return [c for c in cat_names if StyleCategoryClassifier._is_valid_category(c)]
        except Exception as e:
            logger.debug("Non-critical error loading data: %s", e)
        
        # 回退：尝试从文本中提取类别名
        for cat in StyleCategory:
            if cat.value in response.lower():
                return [cat]
        
        return []
    
    @staticmethod
    def _is_valid_category(name: str) -> bool:
        """检查类别名是否有效。"""
        for cat in StyleCategory:
            if cat.value == name.lower().replace(" ", "_").replace("-", "_"):
                return True
        return False

    @staticmethod
    def _build_rag_index(mj_db: dict) -> Optional[tuple]:
        """从 MJ 关键词数据库构建 RAG 检索索引（TF-IDF + 余弦相似度）。

        每个 MJ 关键词是一条文档，标签 = 所属类别。
        用于提升分类精度：相似 prompt 的关键词类别会投票。

        Returns:
            (vectorizer, tfidf_matrix, entry_list) 三元组，或 None
        """
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.metrics.pairwise import cosine_similarity
        except ImportError:
            logger.warning("sklearn not installed, RAG index unavailable")
            return None

        documents = []
        category_labels = []

        for db_key, kws in mj_db.items():
            # 添加每个关键词作为文档
            for kw in kws[:20]:  # 每个类别最多取 20 个
                if len(kw) >= 3:
                    documents.append(kw)
                    category_labels.append(db_key)
            # 添加类别名本身作为文档
            documents.append(db_key.replace("_", " "))
            category_labels.append(db_key)

        if not documents:
            return None

        vectorizer = TfidfVectorizer(
            max_features=500,
            stop_words=None,
            ngram_range=(1, 2),
            analyzer="char_wb",  # 基于字符，支持中文
            max_df=0.8,
        )
        tfidf_matrix = vectorizer.fit_transform(documents)
        return vectorizer, tfidf_matrix, category_labels

    def _vector_search(self, query: str, top_k: int = 5) -> dict[str, float]:
        """向量语义搜索：查询与 MJ 数据库中哪些关键词最相似。

        返回: {db_category_key: score} 得分字典（归一化后）
        """
        # 惰性构建 RAG 索引（首次使用时加载）
        if self._rag_index is None:
            self._rag_index = self.__class__._build_rag_index(
                _load_category_keywords_data()
            )
        if not self._rag_index:
            return {}

        vectorizer, tfidf_matrix, labels = self._rag_index
        try:
            query_vec = vectorizer.transform([query])
            from sklearn.metrics.pairwise import cosine_similarity
            similarities = cosine_similarity(query_vec, tfidf_matrix)[0]

            # 按类别聚合得分
            scores: dict[str, float] = {}
            for i, cat_key in enumerate(labels):
                sim = float(similarities[i])
                if sim > 0.01:
                    scores[cat_key] = scores.get(cat_key, 0.0) + sim

            # 归一化
            if scores:
                max_score = max(scores.values())
                if max_score > 0:
                    scores = {k: v / max_score for k, v in scores.items()}
            return scores
        except Exception as e:
            logger.debug("Vector search failed: %s", e)
            return {}


def _load_category_keywords_data() -> dict:
    """加载原始 MJ 数据库（用于构建 RAG 索引）。"""
    db_path = Path(__file__).parent / "data" / "mj_style_final.json"
    db: dict = {}
    if db_path.exists():
        try:
            with open(db_path, "r", encoding="utf-8") as f:
                db = json.load(f)
        except Exception as e:
            logger.debug("Non-critical error loading data: %s", e)
    return db


# 注册 RAG 索引到 StyleCategoryClassifier（在函数定义之后）—— 惰性初始化，模块导入时不执行
StyleCategoryClassifier._rag_index = None


# StyleCategory → MJ 数据库 key 映射（从 models.py 引入）
from prompt_engine.models import STYLE_CATEGORY_DB_MAP
_STYLE_CAT_DB_MAP: dict[StyleCategory, str] = STYLE_CATEGORY_DB_MAP


def _style_cat_to_db_key(cat: StyleCategory) -> str:
    """将 StyleCategory 枚举转换为 MJ 数据库的 key 字符串。"""
    return _STYLE_CAT_DB_MAP.get(cat, cat.value.replace("_", " ").title().replace(" ", "_"))


# ================================================================
# StyleType → StyleCategory 反向推荐映射
# ================================================================
# 当用户选择一种艺术风格时，推荐对应的 MJ 风格维度，用于指导关键词注入方向
_STYLE_TYPE_CATEGORY_MAP: dict[str, list[StyleCategory]] = {
    "realistic": [
        StyleCategory.CAMERA, StyleCategory.LIGHTING,
        StyleCategory.MATERIAL_PROPERTIES, StyleCategory.PERSPECTIVE,
        StyleCategory.NATURE_AND_ANIMALS,
    ],
    "cartoon": [
        StyleCategory.DRAWING_AND_ART_MEDIUMS, StyleCategory.COLORS_AND_PALETTES,
        StyleCategory.DESIGN_STYLES,
    ],
    "anime": [
        StyleCategory.DRAWING_AND_ART_MEDIUMS, StyleCategory.COLORS_AND_PALETTES,
        StyleCategory.DESIGN_STYLES, StyleCategory.LIGHTING,
    ],
    "oil_painting": [
        StyleCategory.DRAWING_AND_ART_MEDIUMS, StyleCategory.MATERIAL_PROPERTIES,
        StyleCategory.COLORS_AND_PALETTES, StyleCategory.LIGHTING,
    ],
    "watercolor": [
        StyleCategory.DRAWING_AND_ART_MEDIUMS, StyleCategory.COLORS_AND_PALETTES,
        StyleCategory.MATERIALS, StyleCategory.NATURE_AND_ANIMALS,
    ],
    "pixel": [
        StyleCategory.DIGITAL, StyleCategory.DESIGN_STYLES,
        StyleCategory.COLORS_AND_PALETTES,
    ],
    "cyberpunk": [
        StyleCategory.DESIGN_STYLES, StyleCategory.LIGHTING,
        StyleCategory.SFX_AND_SHADERS, StyleCategory.THEMES,
        StyleCategory.MATERIAL_PROPERTIES,
    ],
    "fantasy": [
        StyleCategory.THEMES, StyleCategory.COLORS_AND_PALETTES,
        StyleCategory.DRAWING_AND_ART_MEDIUMS, StyleCategory.LIGHTING,
        StyleCategory.INTANGIBLES,
    ],
    "photography": [
        StyleCategory.CAMERA, StyleCategory.LIGHTING,
        StyleCategory.PERSPECTIVE, StyleCategory.MATERIAL_PROPERTIES,
    ],
    "3d_render": [
        StyleCategory.DIGITAL, StyleCategory.LIGHTING,
        StyleCategory.SFX_AND_SHADERS, StyleCategory.MATERIAL_PROPERTIES,
        StyleCategory.COMBINATIONS, StyleCategory.GEOMETRY,
    ],
    "minimalist": [
        StyleCategory.DESIGN_STYLES, StyleCategory.GEOMETRY,
        StyleCategory.COLORS_AND_PALETTES, StyleCategory.INTANGIBLES,
    ],
    "abstract": [
        StyleCategory.EXPERIMENTAL, StyleCategory.INTANGIBLES,
        StyleCategory.COLORS_AND_PALETTES, StyleCategory.DESIGN_STYLES,
    ],
    "portrait": [
        StyleCategory.CAMERA, StyleCategory.LIGHTING,
        StyleCategory.PERSPECTIVE, StyleCategory.DRAWING_AND_ART_MEDIUMS,
        StyleCategory.MATERIAL_PROPERTIES,
    ],
    "landscape": [
        StyleCategory.NATURE_AND_ANIMALS, StyleCategory.GEOGRAPHY_AND_CULTURE,
        StyleCategory.LIGHTING, StyleCategory.PERSPECTIVE,
        StyleCategory.COLORS_AND_PALETTES,
    ],
}

# 自动注册一条"default"备选
_STYLE_TYPE_CATEGORY_MAP["default"] = [
    StyleCategory.LIGHTING, StyleCategory.MATERIAL_PROPERTIES,
    StyleCategory.COLORS_AND_PALETTES,
]


def recommend_categories_for_style(style: str, top_k: int = 5) -> list[StyleCategory]:
    """根据用户指定的艺术风格，推荐对应的 MJ 风格维度。

    Args:
        style: StyleType 值（如 "oil_painting", "cyberpunk"）
        top_k: 最多返回几个类别

    Returns:
        推荐的 StyleCategory 列表，按相关性降序
    """
    key = style.lower().replace("-", "_")
    if key not in _STYLE_TYPE_CATEGORY_MAP:
        # 尝试反向匹配：遍历已知风格，找到包含该 key 的
        matched = [v for k, v in _STYLE_TYPE_CATEGORY_MAP.items()
                   if key in k or k in key]
        if matched:
            return matched[0][:top_k]
        return _STYLE_TYPE_CATEGORY_MAP["default"][:top_k]
    return _STYLE_TYPE_CATEGORY_MAP[key][:top_k]


# ================================================================
# 反馈驱动权重系统 — 用用户反馈自动优化关键词权重
# ================================================================

# 权重持久化文件路径
_KW_WEIGHTS_PATH = Path(__file__).parent.parent / "keyword_weights.json"


def _load_keyword_weights() -> dict[str, dict[str, float]]:
    """加载关键词权重。返回 {category_db_key: {keyword_lower: weight}}."""
    path = _KW_WEIGHTS_PATH
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.debug("Non-critical error loading data: %s", e)
    return {}


def _save_keyword_weights(weights: dict[str, dict[str, float]]):
    """保存关键词权重."""
    path = _KW_WEIGHTS_PATH
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(weights, f, indent=2, ensure_ascii=False)
    except Exception:
        logger.debug("Silent catch (non-critical): %s", e) if False else None


def _get_weighted_score(category: StyleCategory, keyword: str, weights: dict) -> float:
    """获取带权重的得分乘数（默认 1.0）。"""
    cat_key = category.value
    cat_weights = weights.get(cat_key, {})
    return cat_weights.get(keyword.lower(), 1.0)


def _apply_feedback_to_weights(feedback_path: str = "./feedback_db.json", boost_factor: float = 1.15,
                                reduce_factor: float = 0.85) -> int:
    """从反馈数据库读取反馈，调整关键词权重。

    逻辑：
    - 用户确认了 corrected_categories → 对 prompt 中匹配到的关键词权重 * boost_factor
    - detected_categories 中存在但 corrected 中没有的（假阳性）→ 权重 * reduce_factor
    - rating >= 4 且无 correction → 轻微 boost
    - rating <= 2 且无 correction → 轻微 reduce

    Returns:
        处理的反馈条目数量
    """
    from prompt_engine.feedback import FeedbackStore
    from prompt_engine.classifier import _CATEGORY_KEYWORDS

    store = FeedbackStore(feedback_path)
    weights = _load_keyword_weights()
    cat_kws = _CATEGORY_KEYWORDS if _CATEGORY_KEYWORDS else _load_category_keywords()
    count = 0

    for entry in store._entries:
        if not entry.rating:
            continue
        prompt_lower = entry.prompt.lower()
        count += 1

        # 分解 prompt 中的单词
        prompt_words = set(re.findall(r"[a-zA-Z\u4e00-\u9fff]+", prompt_lower))

        if entry.corrected_categories:
            # 有修正：boost corrected, reduce detected-but-wrong
            corrected_set = set(entry.corrected_categories)
            detected_set = set(entry.detected_categories)

            for cat_name in corrected_set:
                if cat_name not in weights:
                    weights[cat_name] = {}
                # 寻找匹配的关键词并 boost
                best_kw = _find_matching_keyword_in_prompt(prompt_words, cat_name, cat_kws)
                if best_kw:
                    old_w = weights[cat_name].get(best_kw, 1.0)
                    weights[cat_name][best_kw] = round(min(old_w * boost_factor, 3.0), 4)

            for cat_name in detected_set - corrected_set:
                if cat_name not in weights:
                    weights[cat_name] = {}
                best_kw = _find_matching_keyword_in_prompt(prompt_words, cat_name, cat_kws)
                if best_kw:
                    old_w = weights[cat_name].get(best_kw, 1.0)
                    weights[cat_name][best_kw] = round(max(old_w * reduce_factor, 0.1), 4)
        elif entry.rating >= 4:
            # 高分且无修正：轻微 boost 检测到的类别
            for cat_name in entry.detected_categories:
                if cat_name not in weights:
                    weights[cat_name] = {}
                weight = weights[cat_name].get(cat_name, 1.0)
                weights[cat_name][cat_name] = round(min(weight * 1.05, 2.0), 4)
        elif entry.rating <= 2:
            # 低分且无修正：轻微 reduce 检测到的类别
            for cat_name in entry.detected_categories:
                if cat_name not in weights:
                    weights[cat_name] = {}
                weight = weights[cat_name].get(cat_name, 1.0)
                weights[cat_name][cat_name] = round(max(weight * 0.9, 0.1), 4)

    _save_keyword_weights(weights)
    return count


def _find_matching_keyword_in_prompt(
    prompt_words: set[str], cat_name: str, cat_kws: dict
) -> str | None:
    """在 prompt 中找一个匹配该类别关键词的最优关键词。"""
    for cat_enum, kws in cat_kws.items():
        if cat_enum.value == cat_name:
            for kw in kws:
                kw_lower = kw.lower()
                kw_parts = kw_lower.split()
                # 检查是否至少部分匹配
                matching = sum(1 for p in kw_parts if p in prompt_words)
                if matching >= len(kw_parts) * 0.5 and matching > 0:
                    return kw_lower
                    # 优先返回中文同义词
            for syn in _CATEGORY_DESCRIPTIONS.get(cat_enum, "").split("、"):
                syn = syn.strip()
                if syn and syn in " ".join(prompt_words):
                    return syn
                break
    return None


# 全局权重缓存
_KEYWORD_WEIGHTS: dict[str, dict[str, float]] | None = None


def _get_weights() -> dict[str, dict[str, float]]:
    """获取全局权重（惰性加载）."""
    global _KEYWORD_WEIGHTS
    if _KEYWORD_WEIGHTS is None:
        _KEYWORD_WEIGHTS = _load_keyword_weights()
    return _KEYWORD_WEIGHTS


def _invalidate_weight_cache():
    """让权重缓存失效（新反馈应用后调用）."""
    global _KEYWORD_WEIGHTS
    _KEYWORD_WEIGHTS = None
