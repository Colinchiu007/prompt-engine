# PM-PRD v0.19.0 — 缓存持久化 + 性能优化

## 概述

v0.19.0 聚焦「后端核心优化」，解决 3 个问题：

| 问题 | 现状 | 影响 |
|------|------|------|
| 重启丢缓存 | `_PromptCache` 是内存 dict，服务重启后清空 | 每次部署后前 N 次请求无缓存，多花 $0.01-0.03/条 |
| 简单 Prompt 也用 LLM | creative_level 1-10 全部走 LLM | 约 60% 的简单请求（< 5 字描述）没必要调 LLM |
| 模糊匹配太粗糙 | `_similarity()` 仅用 set inclusion，阈值 0.7 | 语义相似但字面不同的 prompt 无法命中缓存 |

## 方案

### F1: SQLite 缓存持久化

**之前**：`_PromptCache: dict[tuple, OptimizeResult]` — 进程内存，重启丢失

**之后**：

```
prompt_engine/cache.py
├── SqlitePromptCache         # SQLite 持久化缓存（主）
│   ├── get(key) → result     # 读取
│   ├── set(key, result)      # 写入
│   ├── stats() → dict        # 命中/大小/条目数
│   └── vacuum()              # TTL 过期清理
├── MemoryPromptCache         # 内存缓存（次，作为 SQLite 的 L1 加速）
```

**缓存键**：`(prompt_hash, platform, creative_level, max_length, negative_prompt, num_candidates)`

**SQLite Schema**：
```sql
CREATE TABLE prompt_cache (
    cache_key TEXT PRIMARY KEY,       -- sha256(prompt + params)
    prompt TEXT NOT NULL,             -- 原始 prompt
    platform TEXT NOT NULL,
    creative_level INTEGER,
    max_length INTEGER,
    negative_prompt TEXT DEFAULT '',
    result_json TEXT NOT NULL,        -- OptimizeResult 序列化
    created_at REAL NOT NULL,         -- time.time()
    hit_count INTEGER DEFAULT 1,
    ttl_hours INTEGER DEFAULT 48
);
CREATE INDEX idx_cache_created ON prompt_cache(created_at);
```

**TTL**：默认 48 小时过期，`vacuum()` 清理过期条目（启动时 + 每 100 次写入触发）。

**降级**：SQLite 不可用时自动回退到 MemoryPromptCache。

### F2: 低创意模板直出（免 LLM）

**之前**：`optimize()` 对任何 creative_level 都调 LLM。

**之后**：

```python
if request.creative_level <= 3:
    # 用 Prompt-as-Code 模板引擎直出，零 LLM 调用
    rendered = render_template(request.prompt, request.platform, request.style)
    return OptimizeResult(optimized_prompt=rendered, tokens_used=0, ...)
```

**简单模式**：初始化时加载一次 `styles.yaml` + `wildcards.yaml`，模板内嵌变量替换（不走 DSL 解析器，避免依赖）。7 个策略各提供一个"简单模式"模板。

**阈值**：
| creative_level | 引擎 | 耗时 |
|:-------------:|------|:----:|
| 1-3 | 模板直出（零 LLM） | < 10ms |
| 4-6 | 标准 LLM | ~4s |
| 7-10 | 详细 LLM | ~7s |

### F3: 基于 TF-IDF 的缓存相似匹配

**之前**：`_similarity()` = 字符串标准化 + set inclusion，阈值 0.7。

**之后**：利用已有的 `scikit-learn` (TfidfVectorizer) 做余弦相似度：

```python
def _similarity(a: str, b: str) -> float:
    # 精确匹配快速路径
    if a.strip().lower() == b.strip().lower():
        return 1.0
    # TF-IDF 余弦相似度
    vectorizer = TfidfVectorizer(analyzer='char', ngram_range=(2, 3))
    tfidf = vectorizer.fit_transform([a, b])
    return (tfidf * tfidf.T).A[0, 1]
```

**效果**：
| 场景 | 旧匹配 | 新匹配 |
|------|:------:|:------:|
| "a cat" vs "a cat" | 1.0 ✅ | 1.0 ✅ |
| "a majestic cat" vs "a cat" | 0.8 ✅ | 0.85 ✅ |
| "a sleeping cat" vs "a cat sitting" | 0.8 ✅ | 0.75 ✅ |
| "a dog" vs "a cat" | 0.8 ❌（误判）| 0.50 ✅（降低） |

**优化**：惰性初始化 vectorizer（首次调用时创建），缓存 vectorizer 实例。

## 验收标准

- [ ] F1: 缓存写入 SQLite 后重启服务，相同 prompt 仍能命中
- [ ] F1: TTL 过期条目被 `vacuum()` 清理
- [ ] F1: SQLite 不可用时自动降级到内存缓存
- [ ] F1: 缓存统计 API (`/v1/cache/stats`) 返回条目数/命中率/大小
- [ ] F2: creative_level 1-3 的请求不调用 LLM，耗时 < 10ms
- [ ] F2: creative_level 4+ 的请求行为不变
- [ ] F2: 各平台（MJ/SD/DALL·E/通义/文心/即梦/通用）都支持简单模板
- [ ] F3: 余弦相似度比旧 set inclusion 更准确（测试验证）
- [ ] 全部 230+ 测试通过
- [ ] CHANGELOG/AGENTS/README 同步更新

## 不破坏的范围

- 所有现有 API 签名不变
- 缓存键格式不变（只是后端从 dict 换成 SQLite）
- 现有测试无需修改
- 未命中缓存时行为完全一致
