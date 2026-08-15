## 1. 评估器误伤修复（负样本校准前置）

- [ ] 1.1 `missing_audio` 改为显式音频需求判定：batch 层仅在正文含音频意图词（sound design/audio cue 等显式词）时检查；纯视觉/静态形态默认 N/A 不扣分（`video_prompt_engine/evaluator.py` 违规检查段）
- [ ] 1.2 `missing_trailer` 判据扩展：识别控制段形态（Duration:/Aspect ratio:/ONE CONTINUOUS SHOT/CUT n 等）即视为精修形态，不再强制 `NON-IP` 字面量
- [ ] 1.3 长度带支持来源/目标双口径：评测用户输入时长度仅提示不扣分（或按语料形态选带），引擎自产输出保留现行带
- [ ] 1.4 六要素词表扩充：style 增加 cinematography/documentary/moody/haze/blur/grain 等；color 增加具体色词（red/blue/gold/black/white/dark 等）
- [ ] 1.5 回归测试：用 258 条 Higgsfield 语料复跑分布，确认 max>58.3 上限松动且 batch 层长度失败显著下降

## 2. 语料目录规范与校验门禁

- [ ] 2.1 新增 `scripts/build_corpus_index.py`：glob 合并 `knowledge/corpus/**/*.json`，统一去重（prompt_text 保留首条）→ 生成归一化合并产物
- [ ] 2.2 校验逻辑：必填字段（id/prompt_text/language/tier 分类）、prompt_text ≥50 字符、tier 白名单（refined/batch/variant/asset）、quality_score 0-10；默认 warning 跳过 + 汇总，`--strict` fail-closed
- [ ] 2.3 loader 双入口接入：`build_corpus_index.py` 产物作为 extra_path 喂入 `load_seed_video_prompts`，主文件原位兼容
- [ ] 2.4 新增 `knowledge/corpus/` 目录规范示例（`higgsfield/README.md` 或示例 JSON），文档化扩充流程

## 3. 负样本资产与格式扩展

- [ ] 3.1 条目格式扩展：loader 解析可选字段 `corpus_type`（positive/negative）、`failure_tags`（对齐 failure_patterns.json）、`applicable_to`（few-shot/eval/both，默认 few-shot）；缺失字段按 positive+few-shot 归一
- [ ] 3.2 新增 `knowledge/seed_failure_samples.json`：首批 10-20 条批量抽卡层失败样本（曝光/死中心构图/风格污染/缺音频/时间轴断裂等，带 failure_tags 与预期违规标签）
- [ ] 3.3 负样本零回归锚定：旧条目无新字段时加载与检索行为不变

## 4. few-shot 负样本排除

- [ ] 4.1 `rag_retriever` 检索注入前过滤 `corpus_type=negative` 或 `applicable_to` 不含 few-shot 的条目（过滤放 `_format_section` 之前，检索路径仍可访问）
- [ ] 4.2 回归测试：正样本正常注入、负样本不进 few-shot 段、向量/关键词检索单独访问负样本正常

## 5. evaluator 负样本校验模式

- [ ] 5.1 新增 `evaluate_negatives(samples)` 独立入口：按 `failure_tags` 与 evaluate() 触发 violations 匹配，输出每类失败模式 {recall, hits, misses, false_positives}
- [ ] 5.2 常规评分路径零影响：未启用校验模式时 evaluate/select_best 行为不变
- [ ] 5.3 回归测试：用 seed_failure_samples 跑校验模式，断言召回统计结构正确、漏检明细可读

## 6. 文档与全量回归

- [ ] 6.1 CHANGELOG 记录本 change；`docs/VIDEO-PROMPT-ENGINE-QUALITY-EVAL-2026-08-15.md` 补充"修复后复测"小节
- [ ] 6.2 全量测试通过（视频引擎 + 图片引擎零回归），语料分布复跑数字写入 CHANGELOG
- [ ] 6.3 openspec sync 将 delta spec 合并入 main spec（video-prompt-engine），归档 change
