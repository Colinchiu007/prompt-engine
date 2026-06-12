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
    """比特级分类器：将 N 分类拆解为 d 个二分类（需要 torch 可选安装）。"""
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
# Style Category Classifier — MJ 27 维度零样本分类
# ================================================================

# 每个 StyleCategory → MJ 数据库关键词（取前 N 个作为匹配种子）
_CATEGORY_KEYWORDS: dict[StyleCategory, set[str]] = {}

# 每个 StyleCategory → 描述性关键词（LLM 理解用）
_CATEGORY_DESCRIPTIONS: dict[StyleCategory, str] = {
    StyleCategory.LIGHTING: "光照效果、光线类型、照明方式、阴影、辉光、体积光",
    StyleCategory.MATERIAL_PROPERTIES: "材质属性、表面质感、透明度、反射、折射、光泽度",
    StyleCategory.MATERIALS: "建筑材料、物体材质、塑料、金属、织物、木材、石材",
    StyleCategory.DIMENSIONALITY: "维度表现、2D/3D/2.5D、立体感、空间深度",
    StyleCategory.COLORS_AND_PALETTES: "色彩方案、色调、调色板、互补色、类似色",
    StyleCategory.RAINBOW_OF_COLORS: "彩虹色、全色谱、丰富色彩、渐变色彩",
    StyleCategory.COMBINATIONS: "色彩组合、特殊色彩效果、发光材质、珍珠色",
    StyleCategory.CAMERA: "相机类型、镜头、摄影技法、光圈、焦距、拍摄手法",
    StyleCategory.PERSPECTIVE: "透视角度、视角、构图方式、仰视、俯视、鱼眼",
    StyleCategory.STRUCTURAL_MODIFICATION: "结构变形、螺旋、几何扭曲、抽象形态",
    StyleCategory.NATURE_AND_ANIMALS: "自然景观、动物、植物、生态系统、野外",
    StyleCategory.OBJECTS: "具体物体、道具、日常物品、机械、电子元件",
    StyleCategory.OUTER_SPACE: "太空、星空、星球、宇宙、星际、银河",
    StyleCategory.GEOMETRY: "几何图形、图案、多面体、对称、伊斯兰几何",
    StyleCategory.GEOGRAPHY_AND_CULTURE: "文化风格、地域特色、民族、历史时期、建筑传统",
    StyleCategory.DRAWING_AND_ART_MEDIUMS: "绘画媒介、艺术技法、水彩、油画、素描、版画",
    StyleCategory.SFX_AND_SHADERS: "视觉特效、着色器效果、光效、粒子、后期处理",
    StyleCategory.THEMES: "主题氛围、情绪、概念、美学运动、亚文化",
    StyleCategory.INTANGIBLES: "抽象概念、不可见的、量子、能量、光、电磁",
    StyleCategory.TV_AND_MOVIES: "影视参考、电影风格、电视剧、动画、漫画",
    StyleCategory.SONG_LYRICS: "歌词风格、音乐相关、歌词意象、旋律视觉化",
    StyleCategory.DESIGN_STYLES: "设计风格、艺术运动、装饰艺术、极简、波普",
    StyleCategory.DIGITAL: "数字艺术、像素艺术、电子游戏风格、CGI",
    StyleCategory.EXPERIMENTAL: "实验风格、前卫、概念艺术、非常规",
    StyleCategory.EMOJIS: "Emoji 风格、表情符号、Unicode 符号",
    StyleCategory.MISCELLANEOUS: "杂项、其他、特殊渲染效果",
}


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
        except Exception:
            pass
    # MJ 类别名 → StyleCategory 枚举映射 (区分大小写，使用数据库中的原始 key)
    CAT_MAP = {
        "Lighting": StyleCategory.LIGHTING,
        "Material_Properties": StyleCategory.MATERIAL_PROPERTIES,
        "Materials": StyleCategory.MATERIALS,
        "Dimensionality": StyleCategory.DIMENSIONALITY,
        "Colors_and_Palettes": StyleCategory.COLORS_AND_PALETTES,
        "Combinations": StyleCategory.COMBINATIONS,
        "Camera": StyleCategory.CAMERA,
        "Perspective": StyleCategory.PERSPECTIVE,
        "Structural_Modification": StyleCategory.STRUCTURAL_MODIFICATION,
        "Nature_and_Animals": StyleCategory.NATURE_AND_ANIMALS,
        "Objects": StyleCategory.OBJECTS,
        "Outer_Space": StyleCategory.OUTER_SPACE,
        "Geometry": StyleCategory.GEOMETRY,
        "Geography_and_Culture": StyleCategory.GEOGRAPHY_AND_CULTURE,
        "Drawing_and_Art_Mediums": StyleCategory.DRAWING_AND_ART_MEDIUMS,
        "SFX_and_Shaders": StyleCategory.SFX_AND_SHADERS,
        "Themes": StyleCategory.THEMES,
        "Intangibles": StyleCategory.INTANGIBLES,
        "TV_and_Movies": StyleCategory.TV_AND_MOVIES,
        "Song_Lyrics": StyleCategory.SONG_LYRICS,
        "Design_Styles": StyleCategory.DESIGN_STYLES,
        "Digital": StyleCategory.DIGITAL,
        "Experimental": StyleCategory.EXPERIMENTAL,
        "Emojis": StyleCategory.EMOJIS,
        "Miscellaneous": StyleCategory.MISCELLANEOUS,
    }
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
    
    # 第二步：英文关键词匹配
    # 注意：Song_lyrics / Experimental / Emojis 类别的数据库是文本内容而非风格标签，跳过英文匹配
    en_parts = re.findall(r'[a-zA-Z\-_]{3,}', prompt_lower)
    for category, kws in cat_kws.items():
        if category in (StyleCategory.SONG_LYRICS, StyleCategory.EXPERIMENTAL, StyleCategory.EMOJIS, StyleCategory.TV_AND_MOVIES):
            continue
        for kw in kws[:30]:  # 扩大检查范围
            kw_lower = kw.lower()
            for part in kw_lower.split():
                if len(part) >= 3 and part in prompt_lower:
                    scores[category] = scores.get(category, 0.0) + 0.8
    
    # 合并结果
    if scores:
        max_score_val = max(scores.values())
        if max_score_val > 0:
            normalized = {k: v / max_score_val for k, v in scores.items()}
            categories = [k for k, v in normalized.items() if v >= max_score * 0.3]
            conf = max(normalized.values())
            
            # 收集每个类别匹配的关键词
            for cat in categories:
                matched_kws = [
                    kw for kw in cat_kws.get(cat, [])
                    if any(pw.lower() in prompt_lower for pw in kw.lower().split() if len(pw) >= 3)
                ]
                keywords_found[cat.value] = list(set(matched_kws))[:5]
            return categories, keywords_found, conf
    
    return [], keywords_found, 0.0


def _build_llm_prompt(prompt: str, categories: list[StyleCategory]) -> tuple[str, str]:
    """构建 LLM 分类的 prompt 和 system prompt。"""
    cat_list = "\n".join(
        f"- {c.value}: {_CATEGORY_DESCRIPTIONS.get(c, '')}"
        for c in categories
    )
    system = f"""你是一个风格分类专家。将用户的描述分配到 MJ Style Reference 的 27 个风格维度中。

{cat_list}

规则：
1. 一个描述可能对应多个维度（例如 "油画风格的星空" → painting_mediums + outer_space）
2. 输出 JSON 格式：{{"categories": ["cat1", "cat2", ...], "reason": "简要说明"}}
3. 如果描述中没有明显的风格倾向，返回空列表
4. 只输出 JSON，不要其他内容"""
    
    user = f"请分析以下描述的 MJ 风格分类：\n\n{prompt}"
    return system, user


class StyleCategoryClassifier:
    """MJ 27 维度风格分类器 — 关键词匹配 + LLM 零样本分类。
    
    工作流程：
    1. 关键词匹配（快速，~0ms）
    2. 如果关键词匹配得分低且 use_llm=True，调用 LLM 做语义分类
    3. 返回多标签分类结果
    
    不依赖 PyTorch/训练数据，零样本工作。
    """
    
    def __init__(self, llm_chat_func=None):
        """初始化分类器。
        
        Args:
            llm_chat_func: 可选的 LLM 聊天函数，签名 (system: str, user: str) -> str
                           如果不提供，关键词匹配后如果没有找到类别则返回空结果
        """
        self._llm_chat = llm_chat_func
    
    def classify(
        self,
        prompt: str,
        max_categories: int = 5,
        use_llm: bool = True,
    ) -> StyleCategoryResult:
        """对 prompt 进行风格分类。
        
        Args:
            prompt: 原始 prompt 文本
            max_categories: 最多返回几个类别
            use_llm: 是否使用 LLM 做深度分类（当关键词匹配得分低时）
        
        Returns:
            StyleCategoryResult 分类结果
        """
        # 第一步：关键词匹配
        keywords_found: dict[str, list[str]] = {}
        categories, kw_found, confidence = _keyword_match(prompt)
        keywords_found.update(kw_found)
        
        # 如果关键词匹配已有结果，直接返回
        if categories:
            # 按置信度排序
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
        
        # 第二步：LLM 分类（如果启用且提供了 llm 函数）
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
        except Exception:
            pass
        
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

