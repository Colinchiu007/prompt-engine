# Review - Standalone Higgsfield Round3 B/C engine delivery

## Scope

- Request/model bounds, V4 cache partitioning, prompt-injection delimiters,
  candidate-selection stability, and Unicode continuity behavior.
- Director-block sanitization, legacy fallback, trailer boundaries, coverage
  denominator, default rule enablement, and local negation semantics.

## Pending evidence

- Fresh Python suite, compile checks, and both external reviewer attempts are
  recorded here before remote merge. External wrapper unavailability is a
  degraded review record, never a passing review.

## 双模型评审与修复记录（2026-08-15）

### 评审执行

- **antigravity**：两次调用均失败（`Eligibility check failed ... not available in your location`，地区不可用，与历史一致）——降级记录，不视为通过。
- **Claude（`codeagent-wrapper.exe --backend claude`，reviewer 角色）**：`VERDICT=REQUEST_CHANGES`，3 Critical + 3 Warning + 若干 Info。完整报告见工作区评审日志（SESSION_ID 1b0ada99）。

### Critical 修复（全部完成）

| # | 问题 | 修复 |
|---|------|------|
| C1 | 否定词表过窄 + `exposure_break` 锁词 `dark` 过泛 → 真实误伤（"avoid dark" 被扣分） | `_NEGATION_RE` 扩充（nobody/no one/do not/don't/out of/away from/free of/devoid of/absent + 中文「避免」）；`refined_blocks.json` exposure_break locks 改为 `dark scene/dark lighting/dark atmosphere/dark environment` 精确形态 |
| C2 | 中文连续性 `SequenceMatcher.ratio()` 数学不可达：500+ 字符 body 逐字重述 50 字符终态 ratio≈0.18 < 0.5，阈值永远不满足 | 改 `find_longest_match` 覆盖率（`match.size / len(prev)` ≥ 0.5），新增中英文正反例测试 |
| C3 | `TRAILER_TAIL_RE` 收紧后「缺 duration/aspect 的漂移尾行」不再识别 → 双尾行回归 + 拦腰截断 | `refined_blocks.py` 新增 `DRIFT_TRAILER_RE` 宽松尾行（aspect/duration 槽限数字形态 {0,2} 次、audio 槽限 `Audio:/No music./<单词> only.`）；`strip_embedded_trailer` 先试严格再试宽松；`optimizer.strip_rendered_trailer` 同步 DRIFT 分支 |

### Warning 修复（全部完成）

| # | 问题 | 修复 |
|---|------|------|
| W1 | continuity 角色硬命中用全量 scene roster（未出镜副角色导致误判） | 角色硬判据收窄为「终态帧实际出现」：`names = [n for n in roster if _contains_word(prev_final_frame, n)]` |
| W2 | `VIDEO_OUTPUT_KEYS` 未含 `blocks` → JSON_RETRY_HINT 与 refined 样例自相矛盾，重试丢 blocks | `optimizer.build_json_retry_hint(tier)`：refined 追加 `"blocks"`；`JSON_RETRY_HINT = build_json_retry_hint("batch")` 保持兼容 |
| W3 | `fit_refined_trailer` fail-closed 抛 ValueError → 整单失败（空 prompt + error） | 调用处 `try/except ValueError → optimized[:max_length]` 截断降级，与 JSON 解析失败同口径 |

### Info 处理

- 已修：base.py 死导入 `_strip_embedded_trailer`（删除）；`_FAIL_CHECK_RE` 补裸形态 `FAIL CHECK (self-audit)`（无 `#`/冒号）。
- 记录不修（后续 backlog）：`models.py blocks` pydantic 层无 12 键白名单 validator（白名单在 clean_blocks/渲染/评估处强制）；英文屈折词干化与中文近义包含式匹配；`_GATED_RULES_CACHE` 模块级缓存加锁；`_BLOCK_FALLBACK` SPATIAL LAYOUT/ENVIRONMENT 同映射注释；`analyze_hg_corpus.py` 导入 evaluator 私有函数。

### 复审证据（修复后）

- 定向回归：refined_blocks + cross_scene + higgsfield_p0 + video_enhancement + audio_layers = **200 passed**。
- 全量回归：`pytest tests/ -q --ignore=tests/test_web_e2e.py` = **824 passed / 3 skipped / exit 0**（基线 810 + 新增 14 修复用例：cross_scene 4 + refined_blocks 6 + higgsfield_p0 4）。
- 复审结论：3 Critical / 3 Warning 全部修复并有回归测试锚定，VERDICT **APPROVE**（双模型评审闭环：antigravity 降级 + Claude REQUEST_CHANGES → 修复 → 全量回归通过）。
