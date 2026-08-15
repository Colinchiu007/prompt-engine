# 视频语料库扩充机制（正向种子 + 负样本/失败模式）

## Why

现有语料库只有「正向 few-shot 语料」（140 主种子 + 258 条《Hell Grind》精选语料），且扩充路径（`extra_path` 合并、`build_higgsfield_seeds.py` 幂等重建）虽已存在，但**没有规范化入口**：新语料放哪个目录、什么格式、如何校验、负样本如何标记且不污染 few-shot，都没有约定。同时 2026-08-15 质量评估（`docs/VIDEO-PROMPT-ENGINE-QUALITY-EVAL-2026-08-15.md`）已暴露 evaluator 对真实语料形态的系统性误伤（missing_audio / missing_trailer / 长度带），却缺少「失败样本语料」来校准规则与做回归保护。

## What Changes

- **语料目录规范**：新增 `knowledge/corpus/<source>/` 约定（如 `higgsfield/`、`internal/`），构建脚本 glob 合并；既有 `seed_video_prompts.json` / `seed_higgsfield_prompts.json` 保持原位兼容。
- **语料条目格式扩展**：可选新增字段 `corpus_type`（`positive`/`negative`，默认 `positive`）、`failure_tags`（负样本的失败模式标签，对齐 `failure_patterns.json`）、`applicable_to`（`few-shot`/`eval`/`both`，默认 `few-shot`）。旧条目无新字段零回归。
- **负样本资产**：新增 `knowledge/seed_failure_samples.json`（批量抽卡层失败样本，带失败模式标签，如曝光/死中心构图/风格污染/缺音频/时间轴断裂）；`applicable_to=eval` 或 `negative` 条目**默认不进入 few-shot 注入**（防污染生成参考）。
- **evaluator 失败样本校验模式**：新增评估入口对负样本做「规则命中率」统计（evaluator 的违规扣分应命中预期 failure_tags），用于校准阈值与回归保护；不影响既有评分路径。
- **语料校验门禁**：构建/加载时校验必填字段、prompt_text 长度下限、tier 合法值（refined/batch/variant/asset）、重复检测、quality_score 范围；非法条目 fail-closed 或带 warning 跳过（可配置）。
- **扩充即生效**：新增语料 JSON 经 loader 合并加载（关键词兜底路径零改动），向量索引重跑 `build_knowledge_base()` 重建；不新增字段的行为与现在一致。

## Capabilities

### New Capabilities
- 无（语料管理归入既有 `video-prompt-engine` 规格扩展，遵循项目既有 spec 组织）

### Modified Capabilities
- `video-prompt-engine`：扩展「Higgsfield 语料资产化与预算注入」需求（目录规范/格式扩展/负样本资产/校验门禁），并扩展「评估与反馈闭环」需求（负样本规则命中率校验模式）

## Impact

- 文件：`video_prompt_engine/knowledge/`（新增 `corpus/` 规范、`seed_failure_samples.json`）、`video_prompt_engine/loader.py`（字段解析与校验）、`video_prompt_engine/rag_retriever.py`（few-shot 排除 negative）、`video_prompt_engine/evaluator.py`（负样本校验模式）、`scripts/build_higgsfield_seeds.py` / 新增 `scripts/build_corpus_index.py`（目录合并与校验）
- 测试：语料结构/校验/负样本排除/规则命中率统计回归
- 兼容性：旧语料与旧调用零回归；新增字段全可选
