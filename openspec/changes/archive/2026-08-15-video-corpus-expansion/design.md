## Context

现状：语料资产集中在 `knowledge/`（主种子 `seed_video_prompts.json` 140 条 + Higgsfield 语料 `seed_higgsfield_prompts.json` 258 条），
经 `loader.py`（extra_path 合并 + lru_cache）→ `rag_retriever.py`（向量 + 关键词兜底 + 预算注入）→ 优化器 system prompt。
构建：`build_higgsfield_seeds.py` 幂等生成语料，`build.py` 重建 TF-IDF v2 索引。
2026-08-15 质量评估（`docs/VIDEO-PROMPT-ENGINE-QUALITY-EVAL-2026-08-15.md`）暴露 evaluator 对真实语料形态的误伤
（missing_audio/missing_trailer/长度带），但缺少「失败样本语料」驱动规则校准。

## Goals / Non-Goals

**Goals:**
- 语料目录化 + 统一校验门禁（扩充不再靠改脚本硬编码）
- 负样本资产（批量抽卡层失败样本 + failure_tags），默认不进 few-shot 注入
- evaluator 负样本校验模式（规则召回统计），支撑阈值校准与回归保护
- 旧语料/旧调用零回归

**Non-Goals:**
- 不改变 few-shot 预算/截断/前缀去重语义
- 不自动调整 evaluator 阈值（校验模式只输出召回统计，调参决策留人工/后续 change）
- 不做语料再分发许可与版权管理（沿用 P2 归档记录）
- 不迁移既有 `seed_video_prompts.json` / `seed_higgsfield_prompts.json` 文件位置（原位兼容）

## Decisions

1. **目录规范**：新增 `knowledge/corpus/<source>/<name>.json`（示例 `higgsfield/`、`internal/`）；
   新脚本 `scripts/build_corpus_index.py` glob 合并 `corpus/**/*.json` → 生成归一化合并产物；
   loader 保持双入口（主文件 + extra_path），corpus 合并产物作为 extra_path 喂入，避免改 loader 加载契约。
2. **格式扩展**：条目新增可选字段 `corpus_type`（positive/negative）、`failure_tags`（[]，对齐 failure_patterns.json 的 pattern 名）、
   `applicable_to`（few-shot/eval/both，默认 few-shot）；缺失字段按 positive+few-shot 归一，旧语料零回归。
3. **负样本排除**：`rag_retriever` 检索结果注入前过滤 `corpus_type=negative` 或 `applicable_to` 不含 few-shot 的条目；
   过滤放在 `_format_section` 之前（检索可命中，注入排除），保持向量/关键词检索可单独访问。
4. **校验门禁**：`build_corpus_index.py` 统一校验（必填字段/prompt_text ≥50 字符/tier 白名单/重复检测/quality_score 0-10）；
   默认非法条目带 warning 跳过并汇总计数，`--strict` 时 fail-closed；与 Higgsfield 语料去重语义一致（prompt_text 去重保留首条）。
5. **负样本校验模式**：evaluator 新增独立入口 `evaluate_negatives(samples) -> {tag: {recall, hits, misses, false_positives}}`；
   复用 `evaluate()` 的违规扣分 checks，按 `failure_tags` 与触发 violations 匹配；不改评分公式与常规路径。
6. **评估器误伤前置处理**：负样本基线校准前，先应用质量评估报告 §5 的三处判据修复
   （missing_audio 显式音频需求、missing_trailer 控制段识别、长度带双口径）——否则召回基线失真。
   该修复随本 change 一并落地（同一批代码改动）。

## Risks / Trade-offs

- **双入口复杂度**：corpus/ 合并产物 + 既有主文件并存，可能产生重复来源；以 build_corpus_index 合并产物为权威，
  构建时对全部来源统一去重（prompt_text），杜绝重复条目混入。
- **lru_cache 缓存**：loader 结果缓存后新增语料需重启进程或失效缓存；沿用现有 `_load_seed_entries_cached` 语义，
  不在本 change 引入热更新（避免复杂度）。
- **负样本召回率低**：若评估器误伤未完全修复，召回统计会偏低——属预期信号（暴露规则缺口），
  校验模式输出漏检明细便于逐条分析，不当作失败。
- **测试面**：新增语料结构/校验/排除/召回统计四组测试；全量回归锚定零变化。
