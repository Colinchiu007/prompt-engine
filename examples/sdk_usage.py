"""Prompt Engine SDK 使用示例"""
from prompt_engine import Optimizer, OptimizeRequest, PlatformType, StyleType
from prompt_engine import StyleCategoryClassifier


def demo_optimize():
    """正向优化"""
    print("=" * 50)
    print("1. 正向优化")
    print("=" * 50)
    optimizer = Optimizer()

    req = OptimizeRequest(
        prompt="一只猫在窗台上晒太阳",
        platform=PlatformType.MIDJOURNEY,
        style=StyleType.REALISTIC,
    )
    result = optimizer.optimize(req)
    print(f"  输入: {req.prompt}")
    print(f"  输出: {result.optimized_prompt}")
    if result.error:
        print(f"  [注意] {result.error}（请配置 API Key）")
    print()


def demo_classify():
    """风格分类"""
    print("=" * 50)
    print("2. 风格分类（26 维 MJ 风格维度）")
    print("=" * 50)
    classifier = StyleCategoryClassifier()

    prompts = [
        "A serene watercolor painting of mountains at sunset",
        "Cyberpunk city with neon lights and rain",
        "Golden retriever in a wildflower meadow",
    ]
    for prompt in prompts:
        result = classifier.classify(prompt, max_categories=3)
        cats = [c.value for c in result.categories]
        print(f"  输入: {prompt}")
        print(f"  方法: {result.method}  置信度: {result.confidence:.2f}")
        print(f"  类别: {cats}")
        print()


def demo_recommend():
    """风格 → 类别推荐"""
    print("=" * 50)
    print("3. StyleType → StyleCategory 反向推荐")
    print("=" * 50)
    from prompt_engine.classifier import recommend_categories_for_style

    for style in ["oil_painting", "cyberpunk", "landscape"]:
        cats = recommend_categories_for_style(style)
        cat_names = [c.value for c in cats]
        print(f"  {style:15s} → {cat_names}")
    print()


def demo_reverse():
    """逆向工程（需配置视觉模型 API）"""
    print("=" * 50)
    print("4. 逆向工程")
    print("=" * 50)
    from prompt_engine.models import ReverseRequest

    optimizer = Optimizer()
    req = ReverseRequest(
        image_url="https://example.com/photo.jpg",
        platform=PlatformType.GENERIC,
    )
    # 需要配置视觉模型 API Key 才能实际运行
    print("  （需要配置 Vision API Key）")
    print()


def demo_feedback():
    """反馈收集"""
    print("=" * 50)
    print("5. 风格分类反馈")
    print("=" * 50)
    from prompt_engine.feedback import FeedbackStore
    from prompt_engine.models import FeedbackEntry

    store = FeedbackStore()
    entry = FeedbackEntry(
        prompt="a cat sitting on a windowsill",
        detected_categories=["lighting", "nature_and_animals"],
        corrected_categories=["lighting", "nature_and_animals"],
        rating=5,
        method="keyword_match",
        confidence=0.85,
    )
    result = store.submit(entry)
    print(f"  反馈已提交: {result.id}")
    stats = store.stats()
    print(f"  总反馈: {stats.total}, 平均评分: {stats.avg_rating}")
    print()


if __name__ == "__main__":
    demo_optimize()
    demo_classify()
    demo_recommend()
    demo_feedback()
