"""使用示例：作为 Python SDK 调用"""
from prompt_engine import Optimizer, OptimizeRequest, PlatformType, StyleType


def main():
    optimizer = Optimizer()

    # 示例 1：通用优化（中文）
    req1 = OptimizeRequest(prompt="一只猫在窗台上晒太阳", platform=PlatformType.GENERIC)
    result1 = optimizer.optimize(req1)
    print("=== 通用优化（中文）===")
    print(f"输入: 一只猫在窗台上晒太阳")
    print(f"输出: {result1.optimized_prompt}")
    print(f"平台: {result1.platform.value}")
    print(f"模型: {result1.model_used}")
    if result1.error:
        print(f"[注意] {result1.error}（请配置有效的 API Key）")
    print()

    # 示例 2：Midjourney 优化
    req2 = OptimizeRequest(
        prompt="cyberpunk city street at night",
        platform=PlatformType.MIDJOURNEY,
        style=StyleType.CYBERPUNK,
        creative_level=8,
    )
    result2 = optimizer.optimize(req2)
    print("=== Midjourney 优化 ===")
    print(f"输入: cyberpunk city street at night")
    print(f"输出: {result2.optimized_prompt}")
    if result2.error:
        print(f"[注意] {result2.error}（请配置有效的 API Key）")
    print()

    # 示例 3：中英文自适应
    req3 = OptimizeRequest(prompt="a cute puppy", platform=PlatformType.DALLE)
    result3 = optimizer.optimize(req3)
    print("=== DALL·E 优化 ===")
    print(f"输入: a cute puppy")
    print(f"输出: {result3.optimized_prompt}")
    if result3.error:
        print(f"[注意] {result3.error}（请配置有效的 API Key）")


if __name__ == "__main__":
    main()