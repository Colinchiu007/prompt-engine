[codeagent-wrapper]
  Backend: antigravity
  Command: agy -p # 任务：评估器 P0-P2 深水区优化方案分析（只读分析，不写代码）

分析对象：D:/Data/projects/mp-worktrees/pe-round3bc-delivery/video_prompt_engine/evaluator.py（852 行确定性评分器 evaluate()，无 LLM 纯规则）。
请先读该文件 + video_prompt_engine/knowledge/golden_set.json + prompt_engine_core/knowledge/element_keywords.json + prompt_engine_core/knowledge.py。

## 当前实现要点（已核验）
- 评分公式（evaluator.py:614-622）：length 20 + elements_score*30 + has_shot 20 + has_camera 15 + has_motion 15 + fidelity*20，总和 /1.2 归一到 100，再叠加 violations 扣分（-5/-10 直接减）
- violations（dict[str,int]，键覆盖拍平）：excluded_present -10 / swap_source_present -10 / missing_trailer -10 / missing_audio -5 / timeline_missing -5 / timing_break -5 / continuity_break -5 / block_coverage -5 / lock-gated 规则 -5
- 六要素（evaluator.py:572-584）：element_keywords.json 资产（6 要素 × en/zh/ru），命中用子串 t in lower（非词边界），部分命中 score=min(1, hits/3)
- 保真（evaluator.py:598-612）：中文 source 取前 8 个 2-gram 块连续匹配；英文 source 实体 token + 轻量词干（_stem_en）命中率；无 source → 1.0
- _contains_word（evaluator.py:18-30）：词边界 (?<![A-Za-z0-9])...(?![A-Za-z0-9])，只保护英文，中文子串误击（excluded 角色"林晓"会命中"林晓雨"）
- detect_tier（evaluator.py:324-338）：auto 时 shots/NON-IP/FINAL FRAME → refined；>833 词 → refined；其余 batch。而 batch 长度上界 hi=min(max(400, max_length//6), 833)（evaluator.py:399-401）——500-833 词无标记文本判 batch 且长度扣分（联动不一致）
- select_best（evaluator.py:695-720）：只返回 (prompt, meta, score)，同分按违规数 tie-break
- evaluate() 返回（evaluator.py:623-629）：score/checks/tier/violations/advice，无版本/资产指纹字段
- 性能：_contains_word/_strip_reference_markers 对每个词/名字全文 regex 扫描；gated 规则 × 禁词 × 候选数
- 已有护栏：258 语料复测 mean 90.9 / golden set MAE 16.93 / Pearson r 0.913（scripts/eval_golden_set.py）

## 待评估优化方案
P0-1 跨语言保真：中文源→英文 prompt 时 fidelity≈0（20 分项恒丢，忠实翻译与乱写无区分度）。方案：双语实体对齐（知识库双语映射）或"翻译模式"检测后改结构保真（镜头要素/长度比）。
P0-2 中文词边界：_contains_word 对中文加边界判定（如名字后不紧跟汉字），防 excluded 角色子串误击。
P0-3 违规分级量化：violations 升级为 {penalty, count, detail}（timing_break 记超时次数/最大超时秒数；block_coverage 记 ratio），select_best tie-break 按 sum(abs(penalty))。
P0-4 权重校准：golden set 权重网格搜索/线性回归（±20% 步进优化 MAE/Pearson），并把 r≥0.90/MAE≤18 固化为 CI 回归门禁。
P1-1 六要素词边界：子串匹配 → 词边界（防 red→category 类误击，注意中文词表）。
P1-2 detect_tier 阈值单一来源：833 与 batch 上界联动，消除 500-833 误分层双亏区。
P1-3 版本指纹：evaluate() 返回 evaluator_schema_version + 资产 hash，支撑运营后台跨版本评测可比。
P1-4 select_best_detailed：返回候选明细（checks/violations/advice）供运营解释"为什么选它"。
P1-5 性能：body 一次性 token 化（英文 split 集合 + 中文 2-gram 集合），_contains_word 变 O(1) 集合查。
P2-1 次要项：advice 按严重度排序；元素资产基于 258 语料 TF-IDF 自动扩表；_GATED_RULES_CACHE 加锁；空输入显式契约。

## 输出要求
1. 逐方案：可行性（高/中/低）+ 具体实现建议（到函数级）+ 风险 + 测试策略
2. 优先级排序与取舍（哪些合并/砍掉，理由）
3. 你发现的遗漏优化点（本清单外）
4. 兼容性风险：对 258 语料复测 mean 90.9 / golden r 0.913 的可能影响，哪些方案会改变分数分布
5. 格式：Markdown，中文，结论先行，具体到 file:line

  PID: 15840
  Log: D:\Temp\codeagent-wrapper-15840.log
  Web UI: http://localhost:63527
Error: Eligibility check failed: Your current account is not eligible for Antigravity, because it is not currently available in your location.

=== Recent Errors ===
Using stdin mode for task due to: piped input, explicit "-", newline, double-quote, length>800
agy exited with status 1
Log file: D:\Temp\codeagent-wrapper-15840.log (deleted)
