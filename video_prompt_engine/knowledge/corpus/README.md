# 视频提示词语料目录（corpus）

本目录是可扩充的**语料源**：按族/来源分目录存放 JSON 语料，经
`python scripts/build_corpus_index.py` 合并、去重、校验后生成归一化索引
`knowledge/corpus_index.json`，由 `video_prompt_engine/knowledge/loader.py`
自动并入引擎知识库（RAG 检索 + few-shot 注入 + 负样本校验共用）。

## 扩充流程（新增语料三步）

1. **放文件**：在 `corpus/<来源>/<族名>.json` 写入条目数组（见下方字段规范）；
   目录/文件名自由，`*.json` 都会被 glob 收录（构建产物与 README 除外）。
2. **跑门禁**：`python scripts/build_corpus_index.py`（默认 warning 跳过 + 汇总）；
   上线前用 `--strict` 验证零违规：`python scripts/build_corpus_index.py --strict`。
3. **重建向量库**（影响 RAG 向量检索时）：`python scripts/build_video_kb.py`
   或 `python -m video_prompt_engine.knowledge.build`，使 `video_prompts_db`
   索引包含新条目（few-shot 关键词兜底路径无需重建，种子全量加载）。

## 字段规范

| 字段 | 必填 | 取值 |
|------|------|------|
| `id` | ✅ | 全局唯一 |
| `prompt_text` | ✅ | ≥50 字符；同一文本只保留首条（去重键） |
| `language` | ✅ | `en` / `zh` |
| `tier` | ✅ | `refined` / `batch` / `variant` / `asset` |
| `quality_score` | 缺省 5 | 0-10 |
| `corpus_type` | 缺省 `positive` | `positive` / `negative` |
| `applicable_to` | 缺省 `few-shot` | `few-shot` / `eval` / `both` |
| `failure_tags` | 缺省 `[]` | 负样本必填；对齐 `knowledge/failure_patterns.json` 的 `pattern` 名 |
| `meta` | 可选 | 结构化 video 元数据（shots/audio/blocks 等，负样本校验用） |

其他字段（title/description/platform/style/categories/source）可选，随构建产物透传。

## 语义约定

- `corpus_type=negative` 的条目是**失败样本**：不注入 few-shot 参考段，
  不进向量库索引；仅供 `evaluate_negatives()` 校验模式统计召回。
- `applicable_to=eval` 的条目（含负样本）不注入 few-shot；`both` 表示双用。
- 精修/批次族的既有语料（seed_higgsfield_prompts.json）不带新字段，
  按 `positive + few-shot` 归一，零回归。

## 示例

见 `higgsfield/family_samples.json`（节选自《Hell Grind》公开语料，仅演示格式）。
