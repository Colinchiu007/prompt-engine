# Review — higgsfield-p2-corpus-cost-model

日期：2026-08-14
范围：prompt-engine（pe-higgsfield-p0 worktree，branch codex/higgsfield-p2）P2 全量 diff
（seed_higgsfield_prompts.json 语料资产化 + vector_store O(n²) 修复 + _format_section 预算硬化 + 成本模型文档）

## 审查方式
- 按 CCG 双模型要求并行派发 antigravity + Claude
- ⚠️ antigravity：账号所在地区不可用（Eligibility check failed），降级记录（与历史一致）
- ✅ Claude 完整评审（session a884508d-9f49-4b3b-8262-13e7035da83b，输出 D:\Temp\hg-p2-claude-review-out.txt）

## Claude 评审结论
**0 Critical / 5 Warning / 12 Info，verdict: approve（附修改意见）**
- 验证执行：20 项新测试全过；全仓 628 passed / 3 skipped；300 次随机查询 fuzz 新旧向量算法 0 不一致
- 正面确认：O(n²) 修复数学等价、lru_cache 设计合理、platform 语义保持、图片引擎不受影响

## Warning 修复闭环（全部已修 + 回归测试）
- **W1** `_format_section` 预算 < per_item_cap 时静默空注入 → 预算作为第二重截断下限（`cap = min(per_item_cap, budget-used)`），极小预算保证至少注入一条；新增 `test_tiny_budget_injects_at_least_one`
- **W2** 3 条硬上限未文档化 → 删除 `shown >= 3`，条数仅由 budget 约束；docstring 明示；新增 `test_all_short_docs_injected_until_budget`（5 条全注入）+ `test_budget_cutoff_stops_at_first_exceeding`（第 4 条超预算截停）
- **W3** search 下标交叉并发 IndexError → 改 zip 四元组迭代（无下标依赖）
- **W4** index.json 无版本/无重建提示 → 版本化 `{"version":2,"docs":[...]}` + 历史裸列表兼容（schema_version 1/2）+ 陈旧索引启动告警（向量 < 种子条数或 schema 旧 → 提示重跑 build_knowledge_base）；新增 `TestIndexVersioning` 4 项
- **W5** 590 条中 332 条 prompt_text 重复 → build 脚本按 prompt_text 去重（保留首条，seq 仍按文件夹计数），重新生成 258 条 / 3.0MB；测试断言同步更新

## Info 处理
- I1 预算计数不含标题/围栏 → 修复：`used` 计入段头 + 完整 block_full（标题/围栏）
- I4 `_tfidf`/`_cosine` 生产死代码 → 标注 legacy 注释
- I5 冷启动 1.5s → `__init__` 主动 `_ensure_index()` 移到进程启动
- I3 loader categories 共享列表 → `list(e.categories)` 防御拷贝
- I9 归档 task.json CRLF → 恢复 LF（diff 缩到 3 字段）
- I6/I7/I8/I10/I11/I12 记录不阻塞（语料路径硬编码 D:\Temp 仅本机确定性校验、slug 冲突防护、标题序号、截头不截尾取舍、语料再分发许可——已记录待后续）

## 回归
- tests/test_higgsfield_corpus.py 26 项全绿（+8 新增）
- 全量 pytest（不含 web_e2e）：**654 passed, 3 skipped**（评审基线 628 + 26 新增）
- corpus+rag_seed 联动 30 passed

## 结论
Claude 评审 0 Critical，5 项 Warning 全部修复并补回归测试，Info 有选择吸收。
允许合并 → 推送 PR。
