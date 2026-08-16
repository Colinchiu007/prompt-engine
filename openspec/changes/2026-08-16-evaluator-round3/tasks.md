# 评估器 round3 — 任务拆分（按批次，测试先行）

## 批次 A（零分数影响，可并行）
- A1 正则缓存：lru_cache 包两个工厂函数 + 测试（hits>0、currsize 有界、258 bit-identical）
- A2 哨兵脚本：scripts/eval_corpus_258.py + 三路语言判定 + 门禁阈值 + CI step + 注入回归测试
- A3 镜头 instrumentation：shot/camera/motion_types 输出 + 否定感知 + 词表 + 测试（wide close-up→2、a shot of cat→0 但 has_shot、no rotation→0）

## 批次 B（分数微调，依赖 A 完成后的基线复测）
- B1 CJK 词表 v3：element_keywords.json zh 六要素去单字补合成词 + version 3 + 反例测试 + 5 条 zh 语料逐条复测
- B2 zh/ru 长度兜底：detect_tier language 参数 + 三处同步 + missing_audio zh/ru 词 + 测试（2500→refined、1900→batch、无 missing_trailer、音效→无 missing_audio）

## 批次 C（分数调整）
- C1 无 source 缩放封顶：ceiling=90+7*elements_score + 快照测试 + golden 复测（MAE≤15.77、7 条两两不等、短卡不塌）

## 收尾
- T1 全量回归（938 基线）+ golden 复测 + 258 复测重定基
- T2 evaluator_version v0.12 + rest.py 同步
- T3 spec.md 追加 round3 Requirement/Scenario；PRD §13.4 补档
- T4 双模型评审（antigravity 不可用则降级记录）→ PR + CI → 合并 → CCG 归档
