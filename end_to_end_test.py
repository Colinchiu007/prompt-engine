"""端到端测试：调用 xfyun 优化一个提示词"""
import sys
from prompt_engine.models import OptimizeRequest, PlatformType
from prompt_engine.optimizer import Optimizer
from prompt_engine.config import load_config

config = load_config()
print("=== Config loaded ===")
print(f"Provider: {config['llm']['provider']}")
print(f"xfyun model: {config['llm']['xfyun']['model']}")
print(f"xfyun base_url: {config['llm']['xfyun']['base_url']}")
print()

# 测试各平台优化
test_cases = [
    ("一只猫", PlatformType.MIDJOURNEY, None),
    ("a sunset over mountains", PlatformType.STABLE_DIFFUSION, None),
    ("女孩在樱花树下", PlatformType.TONGYI, None),
    ("赛博朋克城市夜景", PlatformType.JIMENG, None),
]

opt = Optimizer(config)

for prompt, platform, style in test_cases:
    print(f"--- Testing: platform={platform.value} prompt='{prompt}' ---")
    req = OptimizeRequest(prompt=prompt, platform=platform)
    try:
        result = opt.optimize(req)
        if result.error:
            print(f"  ⚠️ Error (may be fallback): {result.error[:100]}")
            print(f"  Result: {result.optimized_prompt}")
        else:
            print(f"  ✅ Success: {result.optimized_prompt[:150]}...")
            print(f"     tokens: {result.tokens_used}")
    except Exception as e:
        print(f"  ❌ Exception: {type(e).__name__}: {e}")
    print()
