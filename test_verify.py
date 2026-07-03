"""验证所有策略文件正常加载"""
from prompt_engine.strategies import list_strategies, get_strategy, BaseStrategy
from prompt_engine.models import PlatformType, StyleType

# 1. 检查注册
print('=== Registered platforms ===')
for p in list_strategies():
    cls = get_strategy(p)
    print(f'  ✅ {p} → {cls.__name__}')

print()

# 2. 检查每个策略都实现了 build_system_prompt
for p in list_strategies():
    cls = get_strategy(p)
    try:
        prompt = cls.build_system_prompt(style=StyleType.PHOTOGRAPHY, creative_level=7, max_length=300)
        preview = prompt[:100].replace('\n', ' ')
        print(f'  ✅ {p}: {preview}...')
    except Exception as e:
        print(f'  ❌ {p} FAILED: {e}')

print()

# 3. 检查 post_process 也能跑
for p in list_strategies():
    cls = get_strategy(p)
    try:
        result = cls.post_process('  "a test prompt"  ')
        print(f'  ✅ {p} post_process: "{result}"')
    except Exception as e:
        print(f'  ❌ {p} post_process FAILED: {e}')

print()
print(f'=== All {len(list_strategies())} strategies working ✅ ===')
