"""Prompt Engine CLI — 命令行工具"""
import argparse
import json
import sys
from typing import Optional


def _classify(args):
    """运行风格分类"""
    from prompt_engine.classifier import StyleCategoryClassifier
    from prompt_engine.models import StyleCategory, StyleCategoryResult

    classifier = StyleCategoryClassifier()
    result = classifier.classify(args.prompt, max_categories=args.max_categories)

    # 输出
    output = {
        "method": result.method,
        "confidence": round(result.confidence, 4),
        "categories": [
            {
                "value": c.value,
                "name": _get_category_name(c),
            }
            for c in result.categories
        ],
        "keywords_found": result.keywords_found,
    }

    if args.json:
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        _print_table(result, args.max_categories)


def _get_category_name(cat) -> str:
    """获取风格的中文名称"""
    cn_names = {
        "lighting": "光照效果",
        "material_properties": "材质属性",
        "materials": "材料",
        "dimensionality": "维度感",
        "colors_and_palettes": "色彩与调色板",
        "rainbow_of_colors": "彩虹色",
        "combinations": "组合效果",
        "camera": "摄影与镜头",
        "perspective": "视角与构图",
        "structural_modification": "结构修改",
        "nature_and_animals": "自然与动物",
        "objects": "物体与道具",
        "outer_space": "太空与宇宙",
        "geometry": "几何形状",
        "geography_and_culture": "地理与文化",
        "drawing_and_art_mediums": "绘画与艺术媒介",
        "sfx_and_shaders": "特效与着色器",
        "themes": "主题与氛围",
        "intangibles": "抽象概念",
        "tv_and_movies": "影视参考",
        "song_lyrics": "音乐与歌词",
        "design_styles": "设计风格",
        "digital": "数字艺术",
        "experimental": "实验性",
        "emojis": "Emoji 表情",
        "miscellaneous": "杂项",
    }
    return cn_names.get(cat.value, cat.value.replace("_", " ").title())


def _print_table(result, max_categories=5):
    """格式化输出分类结果"""
    from prompt_engine.models import StyleCategory

    print(f"Method:    {result.method}")
    print(f"Confidence: {result.confidence:.2%}")
    print()

    if not result.categories:
        print("No categories matched.")
        return

    print(f"{'Category':<35} {'中文':<15} {'Matched Keywords'}")
    print("-" * 80)
    for cat in result.categories[:max_categories]:
        name = _get_category_name(cat)
        keywords = result.keywords_found.get(cat.value, [])
        kw_str = ", ".join(keywords[:5]) if keywords else "(none)"
        print(f"{cat.value:<35} {name:<15} {kw_str}")


def _list_categories(args):
    """列出所有 27 个风格维度"""
    from prompt_engine.models import StyleCategory

    print("MJ 27 风格维度:")
    print(f"{'ID':<3} {'English':<35} {'中文'}")
    print("-" * 80)
    for i, cat in enumerate(StyleCategory, 1):
        name = _get_category_name(cat)
        print(f"{i:<3} {cat.value:<35} {name}")


def _optimize(args):
    """运行 prompt 优化"""
    from prompt_engine.optimizer import Optimizer
    from prompt_engine.models import OptimizeRequest, PlatformType

    platform_map = {
        "midjourney": PlatformType.MIDJOURNEY,
        "stable_diffusion": PlatformType.STABLE_DIFFUSION,
        "dalle": PlatformType.DALLE,
        "jimeng": PlatformType.JIMENG,
        "tongyi": PlatformType.TONGYI,
        "yizhang": PlatformType.YIZHANG,
        "generic": PlatformType.GENERIC,
    }

    req = OptimizeRequest(
        prompt=args.prompt,
        platform=platform_map.get(args.platform, PlatformType.GENERIC),
        creative_level=args.creative_level,
    )
    optimizer = Optimizer()
    result = optimizer.optimize(req)

    print(f"Platform: {args.platform}")
    print(f"Creative: {args.creative_level}")
    print(f"\nOriginal: {args.prompt}")
    print(f"Optimized: {result.optimized_prompt}")
    if result.detected_categories:
        print(f"\nDetected Categories:")
        for cat in result.detected_categories:
            name = _get_category_name(cat)
            print(f"  - {cat.value} ({name})")



def _recommend(args):
    """根据艺术风格推荐 MJ 风格维度"""
    from prompt_engine.classifier import recommend_categories_for_style
    from prompt_engine.models import StyleCategory

    cats = recommend_categories_for_style(args.style, top_k=args.max)

    if args.json:
        import json
        output = [{'value': c.value, 'name': _get_category_name(c)} for c in cats]
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        print(f"Style: {args.style}")
        print()
        if not cats:
            print("No recommended categories.")
            return
        print(f"{'Category':<35} {'中文':<15}")
        print("-" * 55)
        for c in cats:
            print(f"{c.value:<35} {_get_category_name(c):<15}")


def _feedback(args):
    """查看或提交风格分类反馈。"""
    from prompt_engine.feedback import get_feedback_store
    from prompt_engine.models import FeedbackEntry

    store = get_feedback_store()

    if args.stats:
        stats = store.stats()
        print(f"Total:      {stats.total}")
        print(f"Rated:      {stats.rated}")
        print(f"Avg Rating: {stats.avg_rating:.2f}")
        print(f"Corrected:  {stats.corrected}")
        print()
        print("Method breakdown:")
        for method, count in stats.method_breakdown.items():
            print(f"  {method}: {count}")
        return

    if args.recent:
        entries = store.recent(args.recent)
        if not entries:
            print("No feedback entries.")
            return
        print(f"{'ID':<10} {'Rating':<7} {'Method':<20} {'Prompt'}")
        print("-" * 70)
        for e in entries:
            prompt_preview = e.prompt[:40] + ("..." if len(e.prompt) > 40 else "")
            print(f"{e.id:<10} {e.rating:<7} {e.method:<20} {prompt_preview}")
        return

    # Submit feedback
    entry = FeedbackEntry(
        prompt=args.prompt,
        detected_categories=args.detected or [],
        corrected_categories=args.corrected or [],
        rating=args.rating,
        method=args.method or "",
        confidence=args.confidence or 0.0,
        notes=args.notes or "",
    )
    entry = store.submit(entry)
    print(f"Feedback submitted: {entry.id}")

def main():
    parser = argparse.ArgumentParser(
        prog="prompt-engine",
        description="图片生成提示词优化引擎 CLI",
    )
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # classify
    p_classify = subparsers.add_parser("classify", help="风格分类")
    p_classify.add_argument("prompt", help="要分析的 prompt 文本")
    p_classify.add_argument("-m", "--max-categories", type=int, default=5,
                           help="最多返回几个类别 (default: 5)")
    p_classify.add_argument("--json", action="store_true", help="JSON 输出")

    # categories
    subparsers.add_parser("categories", help="列出所有风格维度")

    # optimize
    # feedback
    p_feedback = subparsers.add_parser("feedback", help="风格分类反馈 (查看/提交)")
    p_feedback.add_argument("--stats", action="store_true", help="查看统计")
    p_feedback.add_argument("--recent", type=int, nargs="?", const=10, default=0,
                           help="查看最近 N 条反馈 (default: 10)")
    p_feedback.add_argument("prompt", nargs="?", default="", help="被分类的 prompt (提交反馈时)")
    p_feedback.add_argument("-d", "--detected", nargs="*", default=[],
                           help="检测到的类别 (如 lighting design_styles)")
    p_feedback.add_argument("-c", "--corrected", nargs="*", default=[],
                           help="纠正后的类别")
    p_feedback.add_argument("-r", "--rating", type=int, default=0,
                           help="评分 0-5")
    p_feedback.add_argument("-m", "--method", default="",
                           help="分类方法")
    p_feedback.add_argument("--confidence", type=float, default=0.0,
                           help="置信度")
    p_feedback.add_argument("-n", "--notes", default="", help="备注")

    p_optimize = subparsers.add_parser("optimize", help="优化 prompt")
    p_optimize.add_argument("prompt", help="要优化的 prompt 文本")
    p_optimize.add_argument("-p", "--platform", default="generic",
                           choices=["midjourney", "stable_diffusion", "dalle",
                                    "jimeng", "tongyi", "yizhang", "generic"],
                           help="目标平台 (default: generic)")
    p_optimize.add_argument("-c", "--creative-level", type=int, default=5,
                           help="创意等级 1-10 (default: 5)")

    # recommend
    p_recommend = subparsers.add_parser("recommend", help="根据艺术风格推荐 MJ 风格维度")
    p_recommend.add_argument("style", help="艺术风格 (如 oil_painting, cyberpunk)")
    p_recommend.add_argument("-m", "--max", type=int, default=5,
                            help="最多推荐几个类别 (default: 5)")
    p_recommend.add_argument("--json", action="store_true", help="JSON 输出")

    args = parser.parse_args()

    if args.command == "classify":
        _classify(args)
    elif args.command == "categories":
        _list_categories(args)
    elif args.command == "feedback":
        _feedback(args)
    elif args.command == "optimize":
        _optimize(args)
    elif args.command == "recommend":
        _recommend(args)
    else:
        parser.print_help()
        sys.exit(0)


if __name__ == "__main__":
    main()