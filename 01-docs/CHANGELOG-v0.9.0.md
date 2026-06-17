## [v0.9.0] — 2026-06-13

### 新增

- **Prompt 内存缓存池（默认启用）** - 相同 prompt 优化 0ms，tokens 0，费用节约 ≥ 90%

### 技术细节

- `optimizer.py` 新增 `_PromptCache: dict[tuple[str, str], OptimizeResult]`
- `_similarity()` 相似度匹配（string normalization + set inclusion）
- `optimize()` 首层缓存检查，命中返回 duration_ms=0 + tokens_used=0

### 性能指标

- 重复 prompt 命中：0ms, 0 tokens
- 10 次相同优化：从 10 tokens → 1 tokens

### 后续

- v0.9.1 将加入 Redis 缓存（多服务器共享）
- v1.0 将加入 LRU 容量限制
