# 评估器 P0-P2 深水区优化 — 任务清单

## 1. 跨语言保真（P0-1）

- [ ] 1.1 `_detect_translation_mode(source, prompt)` + `_cross_lingual_fidelity`（0.5 要素守恒 + 0.3 镜头结构 + 0.2 长度比），`checks["fidelity_method"]="cross_lingual"`
- [ ] 1.2 测试：zh→en 忠实翻译（要素+镜头全保留）≥0.7；换场景对 ≤0.4；en→en 路径回归不变（fidelity_method="wordlist"/"zh2gram"）

## 2. 中文名字边界（P0-2）

- [ ] 2.1 `_WORD_BOUNDARY_RE` 单一来源（合并 18-30/139-148）；`_contains_name(text, token, known_names)` CJK 长名覆盖守卫
- [ ] 2.2 excluded/swap/continuity 角色名走 `_contains_name`；泛词路径不动
- [ ] 2.3 测试：「林晓」vs「林晓雨站在门口」不命中；vs「林晓走进」命中；character_list 含「林晓雨」时不命中；「他站起」posture 仍命中

## 3. 违规分级量化（P0-3）

- [ ] 3.1 `checks["violations_detail"]`（penalty/count/detail）；timing_break 累计 beat_count/max_diff；block_coverage ratio 入 detail
- [ ] 3.2 `select_best`/optimizer tie-break 升级 `sum(abs(penalty))`
- [ ] 3.3 测试：violations 顶层仍 int；timing_break detail count>1；tie-break A={-10} vs B={-5,-5} → A 胜

## 4. 校准门禁与工具（P0-4）

- [ ] 4.1 pytest golden 门禁（r≥0.90/MAE≤18）+ 258 分布哨兵（mean 跌幅 ≤2.0、≥90 占比跌幅 ≤5pp）
- [ ] 4.2 `scripts/eval_golden_set.py --scan-weights`（729 组合热力图 top10，只读）
- [ ] 4.3 全量权重搜索暂缓原因写入 PRD（封顶效应）

## 5. 六要素词边界（P1-1）

- [ ] 5.1 拉丁词词边界、CJK/西里尔子串；≤3 字符拉丁词严格词边界
- [ ] 5.2 测试：`red` 不命中 `category`；`sun` 不命中 `sunrise`；中文词命中不受影响；258 复测哨兵

## 6. detect_tier 阈值单一来源（P1-2）

- [ ] 6.1 `_batch_hi(max_length)` 单一函数；detect_tier 兜底阈值联动；`checks["tier_auto"]`（marker/length/none）
- [ ] 6.2 auto 长度兜底进 refined 豁免 missing_trailer
- [ ] 6.3 测试：600 词无标记 → refined + 长度 20 + 无 missing_trailer；834 词 → refined；batch 上界与 detect_tier 同一函数

## 7. 版本指纹（P1-3）

- [ ] 7.1 `_EVALUATOR_VERSION="v0.11-deterministic"` + `_asset_fingerprint()`；evaluate() 返回 evaluator_version/assets
- [ ] 7.2 rest.py meta 复用常量
- [ ] 7.3 测试：改资产文件后 hash 变化；rest meta 与常量一致

## 8. select_best_detailed（P1-4）

- [ ] 8.1 `select_best(detail=True)` 返回 4 元组（candidates_info 按分降序）
- [ ] 8.2 测试：winner 与 select_best 一致；明细含 violations/advice

## 9. 剥离去重（P1-5）

- [ ] 9.1 单次剥离下传 `_check_continuity`/`_apply_gated_rules`（签名加 body 参数，None 兜底）
- [ ] 9.2 测试：`[ABSENT] Roko` + continuity/gated 路径不再残留 Roko

## 10. 空输入契约 + 其他 P2

- [ ] 10.1 空/纯空白 → score 0 + checks.empty + advice；测试
- [ ] 10.2 advice 严重度排序；测试顺序
- [ ] 10.3 RU 词表补齐（subject/color/environment）；golden ru 样本 elements ≥3 要素命中；测试
- [ ] 10.4 `_GATED_RULES_CACHE` 哨兵/锁；测试并发加载幂等
- [ ] 10.5 中文 2-gram 虚字归一；测试「了/着/在」去除后命中

## 11. 回归与评审

- [ ] 11.1 全量测试通过（896 基线 + 新增）
- [ ] 11.2 258 语料复测 + golden 复测双门禁（哨兵验收）
- [ ] 11.3 双模型评审（Claude 优先，antigravity 探测）修复 Critical/Warning
- [ ] 11.4 OpenSpec spec 更新（video-prompt-engine 评估需求扩展）
- [ ] 11.5 提交 → PR → CI 绿 → 合并；任务归档
- [ ] 11.6 PRD 补档（§13 评估机制 v0.11）
