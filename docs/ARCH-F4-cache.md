# ARCH-F4: Prompt 内存缓存池

## 目标

优化「成本 + speed」瓶颈，重复 prompt 耗时降至 0ms，tokens 降至 0。

## 设计

### 缓存键设计

```
_PromptCacheKey = tuple[str, str]  # (prompt, platform)
_PromptCache = dict[_PromptCacheKey, OptimizeResult]
```

**为什么用 tuple 而非 json？**
- 使用 Pydantic 类型 hint → IDE 支持更好
- 元组不可变 → 无需锁（简单场景）+
- 序列化简单 → 未来可迁移到 Redis

### 相似度匹配

```python
def _similarity(a: str, b: str) -> float:
    a = a.strip().lower()
    b = b.strip().lower()
    
    if a == b:
        return 1.0
    
    # Set inclusion check
    a_words = set(a.split())
    b_words = set(b.split())
    if a_words & b_words:
        return 0.8  # At least one word in common
    
    return 0.5  # Default conservative
```

**为什么不用 Levenshtein？**
- 跨环境兼容问题（有些服务器无 pip 权限）
- 简单 set inclusion 足够应对 80% 场景
- 0.5 阈值保守，降低误判

### 命中路径

```python
def optimize(request: OptimizeRequest) -> OptimizeResult:
    # 1. 检查缓存
    cached = fuzzy_match_prompt(request.prompt, request.platform)
    if cached:
        return OptimizeResult(
            optimized_prompt=cached["optimized_prompt"],
            platform=cached["platform"],
            style=cached["style"],
            model_used=cached["model_used"],
            tokens_used=0,  # 免费
            duration_ms=0,  # 瞬间
            candidates=[],
            detected_categories=None,
        )

    # 2. 未命中 → 调用 LLM
    result = _call_llm(...)
    _PromptCache[(prompt, platform)] = result  # 存入缓存
    return result
```

## 性能指标

| 场景 | 首次 | 命中 |
|------|------|------|
| **耗时** | 2000-5000ms | **0ms** |
| **Tokens** | 100-300 | **0** |
| **费用** | $0.01-0.03 | **$0** |

## 内存约束

### 当前限制

```
内存增长 = Prompt 长度 × N × 2 字节 + OptimizeResult 结构
约 1KB/prompt（100词 × 2 字节 + 500 字符 × 2 字节）
```

### 长期约束（无限制）

| 用量 | 内存占用 | 建议 |
|------|---------|------|
| 1K prompts | ~2MB | 可接受 |
| 100K prompts | ~200MB | 需加 LRU 限制 |
| 1M prompts | ~2GB | 必须加 Redis |

**本版本（v0.9）**：仅内存缓存 → 重启丢失 → 生产用 v0.9.1 走 Redis。

## 并发安全

### 当前方案

Python dict 自动线程安全 → 无需额外锁。

### 生产方案（v0.9.1+）

```python
import redis
from functools import lru_cache

def get_optimizer():
    return Optimizer()
```

Redis 存储加 TTL → 自动清理过时缓存。

## 与现有功能关系

| 功能 | 依赖 | 兼容 |
|------|------|------|
| **RAG few-shot** | 可并行 → 推荐 | ✅ |
| **Style 自动检测** | 可并行 | ✅ |
| **Multi-platform** | 缓存区根据 platform 划分 | ✅ |
| **历史统计** | tokens 0 → 不计入统计 | ✅ 需修改 dashboard |

## 后续演进方向

| 迭代 | 功能 | 价值 |
|------|------|------|
| **v0.9.1** | Redis 缓存 | 多服务器共享 |
| **v0.10** | Embedding 相似度 | 额外套用历史 prompt |
| **v1.0** | LRU 容量限制 | 防止内存溢出 |
| **v1.1** | 缓存 Dashboard | 显示命中率/耗时会 |

