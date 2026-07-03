"""小黑故事板 — 抽象概念→视觉隐喻的分镜策略

合并自两份实现：
- prompt_engine/strategies/xiaohei_storyboard.py（Python 服务端）
- Story2Video/src/lib/storyboard-prompt.ts（TypeScript 客户端）

取两者优势：
- TS 端更完善的构图→动作→物件映射表（14 动作 / 23+ 物件 / 12 概念规则）
- Python 端结构化模板输出 + 手绘风格约束
"""

import random
from prompt_engine.storyboard.base import StoryboardStrategy, register_storyboard


# ═══════════════════════════════════════════════════════════════
# 8 种构图模式（合并 TS 描述 + Python 描述）
# ═══════════════════════════════════════════════════════════════

COMPOSITION_PATTERNS: dict[str, dict[str, str | list[str]]] = {
    "流程展示": {
        "en": "Workflow flow — step-by-step sequence",
        "zh": "将抽象流程具象化为一条有清晰路径的视觉通道",
        "description": "适合展示步骤、链条、阶段变化。用连接元素（箭头/轨迹）串联多个节点。",
        "applyWhen": ["流程", "步骤", "阶段", "链路", "管道", "cycle", "pipeline"],
    },
    "系统局部": {
        "en": "System partial — cross-section detail",
        "zh": '"管中窥豹"，通过一个局部细节暗示整体系统',
        "description": "适合展示复杂系统的核心机制。不画全貌，聚焦某个代表性截面或交互点。",
        "applyWhen": ["系统", "架构", "结构", "机制", "内核", "engine", "core"],
    },
    "前后对比": {
        "en": "Before/after — Split view or transition",
        "zh": "通过视觉对比呈现变化，左边旧状态，右边新状态",
        "description": "适合展示改进、升级、变革。中间用渐变/断层/桥梁过渡。",
        "applyWhen": ["对比", "升级", "变革", "进化", "优化", "upgrade", "evolution"],
    },
    "角色状态": {
        "en": "Character state — emotional/role embodiment",
        "zh": "通过角色的姿态/表情/环境传递抽象概念的氛围",
        "description": "适合传递情感、态度、文化内涵。角色可以是人/拟人化物件。",
        "applyWhen": ["用户", "体验", "情感", "文化", "角色", "user", "experience"],
    },
    "概念隐喻": {
        "en": "Concept metaphor — visual analogy",
        "zh": "用已知视觉概念类比抽象概念，如'防火墙'='盾牌'",
        "description": "适合解释新技术/复杂概念。找到目标域与源域的映射关系。",
        "applyWhen": ["概念", "隐喻", "类比", "解释", "定义", "concept", "metaphor"],
    },
    "方法分层": {
        "en": "Method layers — stacked layers revealing depth",
        "zh": "将抽象概念按层次展开，底层支撑上层",
        "description": "适合展示层级、依赖、架构。底层大/基础、顶层小/应用。",
        "applyWhen": ["分层", "层级", "架构", "依赖", "堆栈", "layer", "stack"],
    },
    "地图路径": {
        "en": "Map route — journey with landmarks",
        "zh": "将抽象过程映射为一张可导航的地图",
        "description": "适合展示路线、规划、历史演进。标注关键里程碑。",
        "applyWhen": ["路径", "路线", "规划", "旅程", "路线图", "roadmap", "journey"],
    },
    "迷你漫画": {
        "en": "Mini comic panels — narrative sequence",
        "zh": "用连环画分格讲述一个完整的小故事",
        "description": "适合展示因果、场景叙事。2-4 格，每格一个关键帧。",
        "applyWhen": ["叙事", "故事", "场景", "案例", "故事线", "story", "narrative"],
    },
}

# ═══════════════════════════════════════════════════════════════
# 动作库（合并 TS 14 个 + Python 独有的）
# ═══════════════════════════════════════════════════════════════

ACTION_POOL: list[dict[str, str]] = [
    {"zh": "挤压 (squeezing)", "effect": "压缩复杂信息到核心", "motion": "自上而下的压合，伴随形变"},
    {"zh": "剖开 (dissecting)", "effect": "揭示内部结构或本质", "motion": "纵向切开，展示截面"},
    {"zh": "追逐 (chasing)", "effect": "表现竞争或追赶趋势", "motion": "平行或弧线运动，动态模糊"},
    {"zh": "折叠 (folding)", "effect": "合并/收拢分散元素", "motion": "沿中线或螺旋向内折"},
    {"zh": "放大 (magnifying)", "effect": "聚焦局部细节", "motion": "镜头推进或放大镜效果"},
    {"zh": "缩小 (shrinking)", "effect": "纳入更大上下文", "motion": "镜头拉远，周围环境展开"},
    {"zh": "穿透 (piercing)", "effect": "突破障碍或边界", "motion": "质点穿过屏障，伴随碎片/光效"},
    {"zh": "缠绕 (winding)", "effect": "关联/依赖/复杂纠葛", "motion": "螺旋或交织，渐紧"},
    {"zh": "分离 (separating)", "effect": "解耦/拆解/分化", "motion": "从联结状态向多方向扩散"},
    {"zh": "融合 (merging)", "effect": "整合/协同/统一", "motion": "多元素向中心汇聚，边界模糊"},
    {"zh": "弹跳 (bouncing)", "effect": "波动/迭代/试错", "motion": "上下或弹性轨迹，虚线路径"},
    {"zh": "旋转 (spinning)", "effect": "多角度审视/循环", "motion": "绕轴旋转，拖影或多帧叠加"},
    {"zh": "堆叠 (stacking)", "effect": "积累/分级/构建", "motion": "逐层向上或向内排列"},
    {"zh": "拉伸 (stretching)", "effect": "延伸/扩展/桥梁", "motion": "两端反向牵引，弹性形变"},
    {"zh": "搬运 (carrying)", "effect": "转移/移动/承载", "motion": "托举或背负，平衡姿态"},
    {"zh": "组装 (assembling)", "effect": "构建/组合/集成", "motion": "多部件向装配位置移动"},
    {"zh": "测量 (measuring)", "effect": "评估/比较/校准", "motion": "工具比对，刻度对齐"},
    {"zh": "挖掘 (digging)", "effect": "探索/深挖/寻找", "motion": "向下或向内挖掘，土石飞溅"},
    {"zh": "连接 (connecting)", "effect": "关联/接通/组网", "motion": "端点接近，结合部发光"},
    {"zh": "倒出 (pouring)", "effect": "释放/倾泻/传播", "motion": "容器倾斜，内容物流出"},
]

# ═══════════════════════════════════════════════════════════════
# 物件库（合并 TS 23 个 + Python 独有的）
# ═══════════════════════════════════════════════════════════════

OBJECT_POOL: list[dict[str, str]] = [
    {"zh": "纸箱", "symbol": "封装/存储/未知内容", "sceneContext": "桌面或仓库场景，可打开/堆叠"},
    {"zh": "抽屉", "symbol": "收纳/分层/隐藏", "sceneContext": "柜体截面，抽出一层展示内容"},
    {"zh": "漏斗", "symbol": "筛选/集中/转换", "sceneContext": "上方宽口入，下方窄口出，颗粒/流体"},
    {"zh": "天平", "symbol": "平衡/权衡/对比", "sceneContext": "两端托盘，砝码或抽象物体"},
    {"zh": "弹簧", "symbol": "弹性/张力/缓冲", "sceneContext": "压缩或拉伸状态，受力箭头"},
    {"zh": "积木", "symbol": "模块化/组装/搭建", "sceneContext": "不同形状/颜色积木，可组合"},
    {"zh": "镜子", "symbol": "反射/映射/自省", "sceneContext": "镜面倒影，镜像世界轮廓"},
    {"zh": "绳索", "symbol": "连接/约束/承重", "sceneContext": "两端固定，可绷紧或松弛"},
    {"zh": "管道", "symbol": "通道/传输/转换", "sceneContext": "透明或截面管道，内部流体/粒子"},
    {"zh": "齿轮", "symbol": "传动/协同/机械", "sceneContext": "啮合齿轮组，不同大小/转速"},
    {"zh": "磁铁", "symbol": "吸引/排斥/场", "sceneContext": "两极标注，磁感线（虚线弧）"},
    {"zh": "灯泡", "symbol": "灵感/照明/能量", "sceneContext": "发光或熄灭，脑内/环境光"},
    {"zh": "沙漏", "symbol": "时间/流逝/临界", "sceneContext": "上半沙将尽，动态流沙颗粒"},
    {"zh": "拼图", "symbol": "完整/缺失/组合", "sceneContext": "多片拼合或缺一片，互锁结构"},
    {"zh": "树", "symbol": "生长/分支/根基", "sceneContext": "根系+树干+树冠，年轮截面"},
    {"zh": "河流", "symbol": "流动/方向/汇聚", "sceneContext": "源头到入海，支流分叉"},
    {"zh": "门", "symbol": "入口/转折/可能", "sceneContext": "开/关/半掩状态，门后透光"},
    {"zh": "桥", "symbol": "连接/跨越/过渡", "sceneContext": "两岸/两物之间，结构支撑"},
    {"zh": "阶梯", "symbol": "递进/成长/层级", "sceneContext": "逐级上升，不同高度/材质"},
    {"zh": "网", "symbol": "连接/捕获/筛选", "sceneContext": "网格拓扑，节点大小/颜色区分"},
    {"zh": "容器", "symbol": "容纳/容量/边界", "sceneContext": "器皿形状，水位或内容物高度"},
    {"zh": "气球", "symbol": "轻盈/膨胀/上升", "sceneContext": "升空或系留，系绳牵引"},
    {"zh": "锚", "symbol": "稳定/定位/依靠", "sceneContext": "锚链紧绷或松弛，水下/水上"},
    {"zh": "梯子", "symbol": "攀登/层级/通道", "sceneContext": "倾斜靠墙，横档清晰"},
    {"zh": "窗户", "symbol": "视野/透窗/期待", "sceneContext": "窗框内看到外部景象，透光"},
    {"zh": "钟表", "symbol": "时间/节奏/截止", "sceneContext": "表盘指针位置指示关键时间"},
    {"zh": "轨道", "symbol": "路径/导向/预定", "sceneContext": "平行轨道延伸向远方/分叉"},
    {"zh": "信封", "symbol": "信息/传递/秘密", "sceneContext": "封口或展开，信纸露出"},
    {"zh": "钥匙", "symbol": "解锁/关键/入口", "sceneContext": "齿型清晰，插入锁孔或独立"},
]

# ═══════════════════════════════════════════════════════════════
# 概念→构图映射规则（12 条，来自 TS）
# ═══════════════════════════════════════════════════════════════

CONCEPT_COMPOSITION_MAP: list[dict[str, list[str] | str]] = [
    {"concepts": ["竞争", "竞赛", "比赛", "争夺", "race", "compete"], "composition": "前后对比"},
    {"concepts": ["平衡", "权衡", "公平", "equal", "balance"], "composition": "前后对比"},
    {"concepts": ["增长", "成长", "发展", "growth", "grow"], "composition": "角色状态"},
    {"concepts": ["系统", "架构", "框架", "system", "framework"], "composition": "方法分层"},
    {"concepts": ["流程", "步骤", "pipeline", "workflow"], "composition": "流程展示"},
    {"concepts": ["创新", "突破", "革命", "innovation", "break"], "composition": "概念隐喻"},
    {"concepts": ["路线", "规划", "历史", "roadmap", "history"], "composition": "地图路径"},
    {"concepts": ["故事", "叙事", "案例", "story", "case"], "composition": "迷你漫画"},
    {"concepts": ["变化", "转型", "升级", "迭代", "transform"], "composition": "前后对比"},
    {"concepts": ["分析", "研究", "深入", "research"], "composition": "系统局部"},
    {"concepts": ["障碍", "困难", "瓶颈", "barrier"], "composition": "角色状态"},
    {"concepts": ["连接", "关系", "沟通", "connect"], "composition": "系统局部"},
]

# 构图→推荐动作
COMPOSITION_ACTION_MAP: dict[str, list[str]] = {
    "流程展示": ["追逐", "分离", "堆叠", "搬运"],
    "系统局部": ["剖开", "放大", "穿透", "挖掘"],
    "前后对比": ["分离", "拉伸", "折叠", "测量"],
    "角色状态": ["缠绕", "挤压", "弹跳", "挖掘"],
    "概念隐喻": ["穿透", "融合", "放大", "连接"],
    "方法分层": ["堆叠", "剖开", "缩小", "组装"],
    "地图路径": ["旋转", "放大", "追逐", "测量"],
    "迷你漫画": ["弹跳", "融合", "分离", "倒出"],
}

# 构图→推荐物件
COMPOSITION_OBJECT_MAP: dict[str, list[str]] = {
    "流程展示": ["漏斗", "管道", "河流", "阶梯", "齿轮", "轨道"],
    "系统局部": ["齿轮", "拼图", "树", "容器", "纸箱", "抽屉"],
    "前后对比": ["天平", "镜子", "桥", "门", "沙漏", "弹簧"],
    "角色状态": ["气球", "弹簧", "磁铁", "树", "锚", "梯子"],
    "概念隐喻": ["灯泡", "镜子", "网", "门", "桥", "钥匙"],
    "方法分层": ["积木", "抽屉", "阶梯", "树", "容器", "梯子"],
    "地图路径": ["河流", "阶梯", "桥", "门", "沙漏", "轨道"],
    "迷你漫画": ["拼图", "绳索", "网", "积木", "纸箱", "信封"],
}

# 构图→配色方案
COLOR_SCHEMES: dict[str, str] = {
    "概念隐喻": "高饱和对比色，戏剧性光照，强调概念反差",
    "流程展示": "渐变色系，冷→暖过渡，清晰的方向性色调",
    "系统局部": "暗色调主体 + 局部高亮，吸引视线到截面",
    "前后对比": "冷暖对比（左冷右暖或反之），中间过渡带",
    "角色状态": "氛围色，与角色情绪匹配（暖=积极，冷=沉思）",
    "方法分层": "底层冷色/低饱和，上层暖色/高饱和，逐层提亮",
    "地图路径": "大地色系基调 + 标志性色彩标注里程碑",
    "迷你漫画": "每格独立配色，统一色调或递进变化",
}

# 构图→构图约束
CONSTRAINT_MAP: dict[str, str] = {
    "概念隐喻": "避免文字标注，让视觉元素本身传递隐喻关系; 主体占画面 60-70%",
    "流程展示": "元素之间保留 15-20% 间距放置连接线; 按阅读方向从左到右或从上到下排列",
    "系统局部": "截面边缘清晰，可用虚框暗示外部整体; 不要画完整系统",
    "前后对比": "中间过渡用渐变/碎裂/光照变化; 双方保持对称构图",
    "角色状态": "角色面部表情清晰可辨; 环境元素不超过 3 种",
    "方法分层": "底层面积 >= 上层 2 倍; 层间用虚线或浅色分隔",
    "地图路径": "标注不超过 5 个关键点; 路径线宽 2-4px 可见",
    "迷你漫画": "每格 2-4 个元素; 格间留白 10-15px",
}

# 构图→关键词
KEYWORD_MAP: dict[str, list[str]] = {
    "概念隐喻": ["analogy", "visual metaphor", "symbolism", "conceptual"],
    "流程展示": ["flow", "sequence", "arrow", "progression", "step-by-step"],
    "系统局部": ["cross-section", "detail", "close-up", "cutaway"],
    "前后对比": ["before/after", "split-view", "transition", "comparison"],
    "角色状态": ["portrait", "expression", "mood", "atmosphere", "character"],
    "方法分层": ["layered", "hierarchy", "stack", "depth", "foundation"],
    "地图路径": ["map", "route", "landmark", "path", "navigation"],
    "迷你漫画": ["comic panel", "narrative", "sequential art", "storyboard"],
}


# ═══════════════════════════════════════════════════════════════
# 三步隐喻引擎
# ═══════════════════════════════════════════════════════════════

def _three_step_metaphor(abstract_concept: str) -> dict:
    """三步隐喻法：抽象概念 → 构图匹配 → 动作+物件选择 → 视觉场景

    Args:
        abstract_concept: 抽象概念或场景文字

    Returns:
        包含 composition, action, object, scene 的字典
    """
    concept_lower = abstract_concept.lower()

    # Step 1: 匹配构图模式
    matched_composition = "概念隐喻"
    for entry in CONCEPT_COMPOSITION_MAP:
        if any(c in concept_lower for c in entry["concepts"]):
            matched_composition = entry["composition"]
            break

    # Step 2: 选择动作和物件
    actions = COMPOSITION_ACTION_MAP.get(matched_composition, ["放大"])
    objects = COMPOSITION_OBJECT_MAP.get(matched_composition, ["灯泡"])
    action = random.choice(actions)
    obj = random.choice(objects)

    # Step 3: 构建视觉场景
    obj_detail = next((o for o in OBJECT_POOL if o["zh"].startswith(obj)), None)
    act_detail = next((a for a in ACTION_POOL if a["zh"].startswith(action)), None)
    comp_detail = COMPOSITION_PATTERNS.get(matched_composition, COMPOSITION_PATTERNS["概念隐喻"])

    scene = (
        f"构图：{matched_composition} — {comp_detail['description']}\n"
        f"动作：{action}（{act_detail['motion'] if act_detail else ''}）\n"
        f"物件：{obj}，象征意义：{obj_detail['symbol'] if obj_detail else ''}\n"
        f"场景描述：以【{obj}】为主体，通过【{action}】的动态，表现「{abstract_concept}」的{matched_composition}关系。"
    )

    return {
        "composition": matched_composition,
        "action": action,
        "object": obj,
        "scene": scene,
        "comp_detail": comp_detail,
        "obj_detail": obj_detail,
        "act_detail": act_detail,
    }


# ═══════════════════════════════════════════════════════════════
# 结构化提示词模板
# ═══════════════════════════════════════════════════════════════

STORYBOARD_TEMPLATE = """## Theme
{theme}

## Composition Type
{composition_type} — {composition_desc}

## Core Metaphor
{metaphor}

## Visual Composition
{visual_composition}

## Suggested Elements
- Subject: {subject}
- Action: {action}
- Object: {object}
- Environment: {environment}

## Color Palette
{color_palette}

## Constraints
{constraints}"""


# ═══════════════════════════════════════════════════════════════
# 策略类
# ═══════════════════════════════════════════════════════════════

@register_storyboard("xiaohei_storyboard")
class XiaoheiStoryboardStrategy(StoryboardStrategy):
    """小黑故事板 — 抽象概念到视觉隐喻的手绘插画风格

    适用场景：
    - 需要叙事感和故事性的图像生成
    - 将抽象概念（市场竞争、技术迭代等）可视化
    - 视频分镜设计的 prompt 生成
    """

    display_name = "Ian 小黑插画风"
    description = "抽象概念到视觉隐喻的手绘插画风格，适合叙事感和故事性的图像生成"

    @classmethod
    def compose(cls, concept: str, **options) -> str:
        """将抽象概念转化为生图 prompt"""
        result = cls._compose_internal(concept, **options)
        return result["prompt"]

    @classmethod
    def compose_with_meta(cls, concept: str, **options) -> dict:
        """将抽象概念转化为生图 prompt + 元数据

        Returns:
            {"prompt": str, "metaphor": dict}
        """
        return cls._compose_internal(concept, **options)

    @classmethod
    def compose_batch(cls, scenes: list[str], full_text: str, **options) -> list[str]:
        """批量转化场景"""
        results = cls.compose_batch_with_meta(scenes, full_text, **options)
        return [r["prompt"] for r in results]

    @classmethod
    def compose_batch_with_meta(cls, scenes: list[str], full_text: str, **options) -> list[dict]:
        """批量转化场景，返回逐条元数据"""
        results = []
        # 尝试取 options 中的 composition_type/creative_level
        base_options = {k: v for k, v in options.items() if k != "scene_index"}

        # 对多场景做整体匹配：用 full_text 决定全局构图类型
        global_metaphor = _three_step_metaphor(full_text)
        base_options.setdefault("composition_type", global_metaphor["composition"])

        for i, scene in enumerate(scenes):
            opts = dict(base_options, scene_index=i)
            results.append(cls._compose_internal(scene, **opts))

        return results

    # ── 内部实现 ──────────────────────────────────────────────

    @classmethod
    def _compose_internal(cls, concept: str, **options) -> dict:
        """核心生成逻辑"""
        composition_type = options.get("composition_type")
        creative_level = options.get("creative_level", 5)
        full_text = options.get("full_text", concept)
        scene_index = options.get("scene_index", 0)
        style = options.get("style")

        # 1. 三步隐喻
        metaphor = _three_step_metaphor(concept)
        if composition_type:
            metaphor["composition"] = composition_type

        comp_type = metaphor["composition"]
        comp_info = COMPOSITION_PATTERNS.get(comp_type, COMPOSITION_PATTERNS["概念隐喻"])

        # 2. 视觉描述（英文，面向生图模型）
        visual = (
            f"A minimalist hand-drawn illustration in pure white background. "
            f"A small character performs the action of {metaphor['action']} "
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

        # 4. 约束
        constraints_parts = [
            "纯白背景，手绘插画风格",
            CONSTRAINT_MAP.get(comp_type, "主体清晰，背景简洁"),
        ]
        if creative_level >= 6:
            constraints_parts.append("极简构图，去除冗余元素")
        if creative_level >= 8:
            constraints_parts.append("静态画面，含蓄叙事")

        # 5. 关键词
        keywords = KEYWORD_MAP.get(comp_type, ["hand-drawn", "illustration", "minimalist"])
        if creative_level >= 3:
            keywords_str = ", ".join(keywords)
            constraints_parts.append(f"Keywords: {keywords_str}")

        # 6. 配色描述
        color_palette = COLOR_SCHEMES.get(comp_type, "中性色调，突出主体")
        if creative_level >= 4:
            color_palette += f" | 主色: {colors['main']}, 强调色: {colors['accent']}, 底色: {colors['bg']}"

        # 7. 构建结构化输出
        prompt = STORYBOARD_TEMPLATE.format(
            theme=f"{concept} ({concept})",
            composition_type=comp_type,
            composition_desc=comp_info["en"],
            metaphor=f"The abstract concept of '{concept}' is represented through {metaphor['action']} on a {metaphor['object']}",
            visual_composition=visual,
            subject=f"A character (simple figure with solid black body, white dot eyes, thin legs)",
            action=metaphor["action"],
            object=metaphor["object"],
            environment="Pure white minimal space, no background elements except the essential subject",
            color_palette=color_palette,
            constraints="\n".join(f"- {c}" for c in constraints_parts),
        )

        return {
            "prompt": prompt,
            "metaphor": {
                "composition_type": comp_type,
                "composition_desc": comp_info["description"],
                "action": metaphor["action"],
                "object": metaphor["object"],
                "scene": metaphor["scene"],
                "creative_level": creative_level,
            },
        }
