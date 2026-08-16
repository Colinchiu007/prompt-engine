# 视频提示词 max_length 上限 20000 → 40000

## Why

用户对视频提示词字数诉求持续放宽（前序已 5000→20000）。Multi-Publish 桌面契约层（`video-prompt-engine-contract.js`）将把视频域上限 `videoMaxLengthMax` 从 20000 提到 40000，历史重生成/精修入口会显式携带 `max_length=40000`；引擎侧 `VideoOptimizeRequest.max_length` 当前 `le=20000`，若不同步放开，显式 40000 请求会 422，长导演分镜单（≈5000 词 / 22,871 字符）仍然放不开。

## What Changes

- **`VideoOptimizeRequest.max_length` 边界上浮**：`video_prompt_engine/models.py:80` `le=20000` → `le=40000`；description 同步（精修层 creative_level≥7 上限 40000，对齐契约层 videoMaxLengthMax）。批量层默认 1800、ge=200 不变。
- **feedback `result_prompt` 上限同步**：`models.py:180` `max_length=20000` → `40000`（沿用 5000→20000 时的既有先例：feedback 闭环上限与 max_length 边界上浮对齐，refined 长结果可回传，评审 W2）。
- **注释同步**：`video_prompt_engine/llm/base.py` 与 `prompt_engine_core/llm.py` 的「≤20000 字符」注释更新为 40000；max_tokens 默认 cap 16384 与 `llm.max_tokens_cap` 配置逻辑不动（le=40000 时 max_tokens 理论 80000 仍被 cap 压回，防上游 400）。
- **测试同步**：`tests/test_higgsfield_p0.py` `TestModelsBoundary` 的 20000/20001 边界 → 40000/40001（max_length 与 feedback result_prompt 两处）。
- **规格/文档**：`openspec/specs/video-prompt-engine/spec.md` Requirement「max_length 上限支持至 20,000 字符」→ 40,000；`CHANGELOG.md` 置顶条目。

## Capabilities

### New Capabilities

- 无（归入既有 `video-prompt-engine` 规格）。

### Modified Capabilities

- `video-prompt-engine`：`VideoOptimizeRequest.max_length` 上限 20000 → 40000（精修层/显式顶格路径），feedback `result_prompt` 上限同步；批量默认、评估预算独立 API（`VideoEvaluateRequest.max_length` le=20000）、输入 prompt 2000、max_tokens cap 16384 均不变。

## Impact

- 文件：`video_prompt_engine/models.py`、`video_prompt_engine/llm/base.py`（注释）、`prompt_engine_core/llm.py`（注释）、`tests/test_higgsfield_p0.py`、`openspec/specs/video-prompt-engine/spec.md`、`CHANGELOG.md`。
- 测试：`TestModelsBoundary` 边界回归（40000 accepted / 40001 rejected ×2）+ 全量 pytest 回归（CI 3.11）。
- 兼容性：仅放宽上界，`ge=200`、默认值、tier 默认（batch 1800 / refined 5000 由契约层携带）不变；max_tokens 动态放大仍受 16384 默认 cap 约束，不改变真实 provider 输出上限，只解除校验层 422。
- 不涉及：图片引擎、评估器评分逻辑、RAG/种子库、API 路由形状。
