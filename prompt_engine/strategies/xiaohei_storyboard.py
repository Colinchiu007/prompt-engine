"""
⚠️ DEPRECATED: 请迁移到 prompt_engine.storyboard.xiaohei 模块

旧模块（prompt_engine.strategies.xiaohei_storyboard）将在未来版本移除。
新模块（prompt_engine.storyboard）提供可插拔的 StoryboardStrategy 基类 +
统一注册表 + REST 端点 /v1/storyboard/*。

迁移方式:
  旧: from prompt_engine.strategies.xiaohei_storyboard import XiaoheiStoryboardStrategy
  新: from prompt_engine.storyboard.xiaohei import XiaoheiStoryboardStrategy, get_storyboard_strategy

旧注册: @register("xiaohei_storyboard") → 继承 BaseStrategy
新注册: @register_storyboard("xiaohei_storyboard") → 继承 StoryboardStrategy

此模块保持向后兼容，不会被删除，但不再接受新功能。
"""

import warnings
warnings.warn(
    "prompt_engine.strategies.xiaohei_storyboard is deprecated. "
    "Use prompt_engine.storyboard.xiaohei instead. "
    "See module docstring for migration guide.",
    DeprecationWarning,
    stacklevel=2,
)


import warnings
warnings.warn(
    "prompt_engine.strategies.xiaohei_storyboard is deprecated. "
    "Use prompt_engine.storyboard.xiaohei instead. "
    "See module docstring for migration guide.",
    DeprecationWarning,
    stacklevel=2,
)


"""小黑故事板构图 — 抽象概念→视觉隐喻的提示词策略

复用于 Ian 小黑插画的 3 步隐喻生成法 + 8 种构图模式 + 动作库 + 对象池。
将抽象概念转化为具象的视觉画面描述，适合需要叙事感和隐喻表达的图像生成。

使用方法:
  from prompt_engine.strategies.xiaohei_storyboard import XiaoheiStoryboard
  prompt = XiaoheiStoryboard.compose("市场竞争", composition_type="对比")
"""

from prompt_engine.strategies.base import BaseStrategy, register
from prompt_engine.models import PlatformType, StyleType
import random


# ═══════════════════════════════════════════════════
# 8 种构图模式（reuse from ian-xiaohei-illustrations）
# ═══════════════════════════════════════════════════

COMPOSITION_PATTERNS = {
    "流程展示": {
        "en": "Workflow flow — A step-by-step horizontal or vertical arrangement showing a transformation process",
        "zh": "流程展示型 — 将抽象流程转化为物理流水线，物品沿传送带或管道逐步变化",
    },
    "系统局部": {
        "en": "System partial — A cross-section or zoom-in revealing the inner mechanism of a system",
        "zh": "系统局部型 — 剖开系统外壳展示内部运作机制，用机械结构隐喻抽象关系",
    },
    "前后对比": {
        "en": "Before/after — Split view showing transformation from one state to another",
        "zh": "前后对比型 — 左右或上下分割，展示同一事物在干预前后的状态变化",
    },
    "角色状态": {
        "en": "Character state — A character in a specific emotional/physical state, surrounded by visual metaphors",
        "zh": "角色状态型 — 角色处于某种情绪或状态中，周围物件暗示其内心或处境",
    },
    "概念隐喻": {
        "en": "Concept metaphor — An abstract idea represented through a physical analogy",
        "zh": "概念隐喻型 — 用日常物理场景比喻抽象概念（如用跷跷板比喻平衡）",
    },
    "方法分层": {
        "en": "Method layers — Stacked or nested layers showing a multi-level structure or hierarchy",
        "zh": "方法分层型 — 多层堆叠或嵌套结构，展示层级关系或分类体系",
    },
    "地图路径": {
        "en": "Map route — A journey or decision path visualized as a map with marked routes",
        "zh": "地图路径型 — 将决策过程或发展路径绘制为地图，标注关键节点",
    },
    "迷你漫画": {
        "en": "Mini comic panels — 2-4 sequential panels showing a cause → effect → resolution story",
        "zh": "迷你漫画型 — 2-4 格连环画，依序展示起因→经过→结果",
    },
}

# ═══════════════════════════════════════════════════
# 动作库（reuse from ian-xiaohei-illustrations）
# ═══════════════════════════════════════════════════

ACTION_POOL = [
    "挤压 (squeezing)",
    "剖开 (dissecting)",
    "追逐 (chasing)",
    "放错位置 (misplacing)",
    "拉伸 (stretching)",
    "旋转 (rotating)",
    "搬运 (carrying)",
    "组装 (assembling)",
    "测量 (measuring)",
    "挖掘 (digging)",
    "连接 (connecting)",
    "倒出 (pouring)",
    "堆叠 (stacking)",
    "撕开 (tearing apart)",
]

# ═══════════════════════════════════════════════════
# 对象池
# ═══════════════════════════════════════════════════

OBJECT_POOL = [
    "纸箱", "抽屉", "漏斗", "天平", "弹簧",
    "齿轮", "管道", "梯子", "绳子", "镜子",
    "气球", "沙漏", "门", "窗户", "桥",
    "灯", "钟表", "网", "轨道", "磁铁",
    "积木", "信封", "钥匙",
]


# ═══════════════════════════════════════════════════
# 3 步隐喻生成
# ═══════════════════════════════════════════════════

def _three_step_metaphor(abstract_concept: str) -> dict:
    """3 步隐喻生成：抽象概念 → 物理动作 → 低科技物件
    
    Args:
        abstract_concept: 抽象概念，如"市场竞争""技术迭代"
    
    Returns:
        包含 action, object, composition 的字典
    """
    # 启发式匹配：根据概念关键词推荐构图 + 动作 + 物件
    concept_lower = abstract_concept.lower()
    
    if any(w in concept_lower for w in ["竞争", "竞赛", "比赛", "对战"]):
        return {
            "composition": "前后对比",
            "action": "追逐 (chasing)",
            "object": "漏斗",
            "scene": "两个物体在漏斗轨道上你追我赶",
        }
    elif any(w in concept_lower for w in ["平衡", "权衡", "协调"]):
        return {
            "composition": "概念隐喻",
            "action": "测量 (measuring)",
            "object": "天平",
            "scene": "天平两端承载不同物体，正在寻找平衡点",
        }
    elif any(w in concept_lower for w in ["增长", "成长", "扩大"]):
        return {
            "composition": "流程展示",
            "action": "堆叠 (stacking)",
            "object": "积木",
            "scene": "积木从下到上逐层搭建，越来越高",
        }
    elif any(w in concept_lower for w in ["变化", "转型", "升级", "迭代"]):
        return {
            "composition": "前后对比",
            "action": "组装 (assembling)",
            "object": "齿轮",
            "scene": "旧齿轮被逐步替换为新齿轮，系统正在升级",
        }
    elif any(w in concept_lower for w in ["连接", "关系", "沟通"]):
        return {
            "composition": "系统局部",
            "action": "连接 (connecting)",
            "object": "绳子",
            "scene": "多条绳子将分散的物体连接成网络",
        }
    elif any(w in concept_lower for w in ["分析", "研究", "深入"]):
        return {
            "composition": "系统局部",
            "action": "剖开 (dissecting)",
            "object": "纸箱",
            "scene": "纸箱被剖开一面，展示内部复杂的结构",
        }
    elif any(w in concept_lower for w in ["障碍", "困难", "瓶颈"]):
        return {
            "composition": "角色状态",
            "action": "挖掘 (digging)",
            "object": "门",
            "scene": "角色在紧闭的门前挖掘通道",
        }
    elif any(w in concept_lower for w in ["路径", "路线", "策略"]):
        return {
            "composition": "地图路径",
            "action": "测量 (measuring)",
            "object": "轨道",
            "scene": "多条轨道从起点向不同方向延伸，关键节点有路标",
        }
    else:
        # 随机选择
        comp = random.choice(list(COMPOSITION_PATTERNS.keys()))
        action = random.choice(ACTION_POOL)
        obj = random.choice(OBJECT_POOL)
        return {
            "composition": comp,
            "action": action,
            "object": obj,
            "scene": f"角色正在{action}一个{obj}，隐喻「{abstract_concept}」",
        }


# ═══════════════════════════════════════════════════
# 结构化提示词模板
# ═══════════════════════════════════════════════════

STORYBOARD_TEMPLATE = """## 主题 (Theme)
{theme}

## 构图类型 (Composition Type)
{composition_type} — {composition_desc}

## 核心隐喻 (Core Metaphor)
{metaphor}

## 画面描述 (Visual Composition)
{visual_composition}

## 推荐元素 (Suggested Elements)
- 主体: {subject}
- 动作: {action}
- 物件: {object}
- 环境: {environment}

## 颜色使用 (Color Palette)
- 主色: {main_color}
- 强调色: {accent_color}
- 底色: {background_color}

## 约束 (Constraints)
- 纯白背景，手绘风格
- 画面主体占比 40-60%
- 极简构图，去除冗余元素
- 静态画面，含蓄叙事"""


# ═══════════════════════════════════════════════════
# 策略类
# ═══════════════════════════════════════════════════

@register("xiaohei_storyboard")
class XiaoheiStoryboardStrategy(BaseStrategy):
    """小黑故事板 — 将抽象概念转化为视觉隐喻的提示词策略

    适用场景：
    - 需要叙事感和故事性的图像生成
    - 将抽象概念（市场竞争、技术迭代等）可视化
    - 视频分镜设计的 prompt 生成
    """

    platform = PlatformType.GENERIC

    @classmethod
    def compose(
        cls,
        concept: str,
        composition_type: str | None = None,
        style: StyleType | None = None,
        creative_level: int = 5,
    ) -> str:
        """构建议故事板提示词。

        Args:
            concept: 抽象概念或主题描述
            composition_type: 构图类型（可选，None 自动匹配）
            style: 可选风格类型
            creative_level: 创意等级 1-10

        Returns:
            结构化提示词字符串
        """
        # 1. 自动匹配或指定构图
        metaphor = _three_step_metaphor(concept)
        comp_type = composition_type or metaphor["composition"]
        comp_info = COMPOSITION_PATTERNS.get(comp_type, COMPOSITION_PATTERNS["概念隐喻"])

        # 2. 视觉描述
        visual = (
            f"A minimalist hand-drawn illustration in pure white background. "
            f"A character performs the action of {metaphor['action']} "
            f"on a {metaphor['object']}, creating a visual metaphor for "
            f"'{concept}'. {metaphor['scene']}. "
            f"{comp_info['en']}. "
            f"The composition is clean with 40-60% subject occupancy, "
            f"simple black lines, subtle warm accent colors (red/orange/blue tones only)."
        )

        # 3. 颜色方案
        if creative_level <= 3:
            colors = {"main": "warm orange (#E87D4F)", "accent": "soft red (#D45C5C)", "bg": "pure white (#FFFFFF)"}
        elif creative_level <= 7:
            colors = {"main": "warm orange (#E87D4F)", "accent": "deep blue (#4A7BA7)", "bg": "pure white (#FFFFFF)"}
        else:
            colors = {"main": "deep blue (#4A7BA7)", "accent": "vibrant orange (#E87D4F)", "bg": "pure white (#FFFFFF)"}

        # 4. 构建结构化输出
        theme_cn = concept
        theme_en = concept  # 实际可做翻译
        subject = f"A character (simple figure with solid black body, white dot eyes, thin legs)"

        return STORYBOARD_TEMPLATE.format(
            theme=f"{theme_en} ({theme_cn})",
            composition_type=comp_type,
            composition_desc=comp_info["en"],
            metaphor=f"The abstract concept of '{concept}' is represented through the physical action of {metaphor['action']} on a {metaphor['object']}",
            visual_composition=visual,
            subject=subject,
            action=metaphor["action"],
            object=metaphor["object"],
            environment="Pure white minimal space, no background elements except the essential subject",
            main_color=colors["main"],
            accent_color=colors["accent"],
            background_color=colors["bg"],
        )

    @classmethod
    def build_system_prompt(
        cls,
        style: StyleType | None = None,
        creative_level: int = 5,
        max_length: int = 1000,
        negative_prompt: str | None = None,
    ) -> str:
        """构建系统提示词 — 指导 LLM 用故事板方法论优化 prompt"""
        style_text = f"，风格：{style.value}" if style else ""

        return f"""You are a storyboard prompt expert specializing in the "abstract→visual metaphor" methodology.

Your task is to transform abstract concepts into structured visual prompts using this 3-step method:
1. **Abstract concept → Physical action** — Convert the idea into a tangible physical action
2. **Physical action → Low-tech object** — Choose a simple everyday object as the metaphor vehicle
3. **Object → Character action** — Describe a character performing the action with the object

## Composition Types (choose the best fit)
- Workflow flow: Horizontal/vertical transformation process
- System partial: Cross-section revealing inner mechanism
- Before/after: Split view comparing two states
- Character state: Character in metaphorical surroundings
- Concept metaphor: Physical analogy for abstract idea
- Method layers: Stacked/nested hierarchical structure
- Map route: Decision path as map with markers
- Mini comic panels: 2-4 sequential cause→effect→resolution

## Output Structure
Follow this 7-field format:
1. **Theme** — The abstract concept in both English and Chinese
2. **Composition Type** — One of the 8 types above with brief explanation
3. **Core Metaphor** — The physical analogy driving the image
4. **Visual Composition** — Detailed scene description (English only)
5. **Suggested Elements** — Subject, action, object, environment
6. **Color Palette** — Limited to warm orange, soft red, deep blue accents on white
7. **Constraints** — Hand-drawn style, minimal, 40-60% subject

## Rules
- Output in ENGLISH for the image generation model
- Use simple, concrete language — avoid abstract terms in the visual description
- Maximum {max_length} characters
- Pure white background, hand-drawn illustration style
- Every element must serve the metaphor — remove anything decorative
{style_text}"""

    @classmethod
    def post_process(cls, raw_output: str, creative_level: int = 5,
                     preferred_categories: list[str] | None = None) -> str:
        """后处理：清理格式，提取核心 prompt 部分"""
        text = raw_output.strip().strip('"').strip("'").strip()

        # 如果输出包含结构化模板，提取视觉描述部分
        if "## 画面描述" in text or "## Visual Composition" in text:
            import re
            # 尝试提取视觉描述段落
            match = re.search(r'(?:## 画面描述|## Visual Composition)\s*\n(.*?)(?:\n##|\Z)', text, re.DOTALL)
            if match:
                return match.group(1).strip()

        # 注入风格关键词
        from prompt_engine.keyword_injector import inject_style_keywords
        return inject_style_keywords(text, creative_level, preferred_categories)
