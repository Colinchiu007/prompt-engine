# 共享内核迁移 Phase 2/3 — 评审记录（2026-08-14）

## 评审方式
- 双模型并行评审 → **降级 Claude 单模型**：antigravity 探测结果 `Eligibility check failed: Your current account is not eligible for Antigravity, because it is not currently available in your location`（地区不可用，403 类），按机制硬化规则降级并记录。
- Claude（codeagent-wrapper backend=claude，reviewer role）对 28KB diff 全量审查，并交叉核对了 core 与两引擎源码、种子数据、config 默认值。

## 发现与处置
| 级别 | 发现 | 处置 |
|------|------|------|
| Critical | core llm `if self.max_tokens_cap:` 守卫残留 → 默认 16384 cap 死代码（W1 回归） | 已修复：去掉守卫，无条件 `min(max_tokens, self.max_tokens_cap or 16384)`；新增 4 项 cap 测试锚定 |
| Major | 图片 list_strategies 排序语义（插入序→字母序）外部可观察 | 已修复：core.registry 新增 `items()` 保序方法，图片包装层按注册序返回，与旧行为一致 |
| Major | 注册键小写归一契约变化（get_strategy 大小写宽容） | 已接受：既有注册名全小写、生产调用方已归一，无行为影响；CHANGELOG 明示 |
| Major | 种子显式 `platform: "generic"` 会被静默改写 generic_video | 已修复：core `load_seed_entries(default_platform=...)` 参数化，显式字段原样保留，仅缺失回退；新增 3 项测试 |
| Minor | compare.py 依赖 optimizer 隐式 re-export | 已修复：直连 `prompt_engine_core.text` |
| Minor | 独立断言正则 `\b` 过宽 | 已修复：改负向前瞻 `(?!_)` |
| Minor | core vector_store 默认平台硬编码 generic_video（图片迁移地雷） | 已修复：构造参数 `default_platform` 化 |
| Minor | 文件尾缺换行 / api_key 重复检查无注释 | 已修复 |

## 验证
- 全量 pytest：**628 passed, 3 skipped, 5 errors**（errors 全为 test_web_e2e 需本地起 8094 web 服务，环境类，与基线一致）