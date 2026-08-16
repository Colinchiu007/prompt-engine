# Tasks

> 状态：实现中，待测试与门禁。

## - [ ] 引擎模型上界 40000
  - [ ] `video_prompt_engine/models.py:80` `max_length` `le=20000` → `le=40000`（description 同步 40000）
  - [ ] `video_prompt_engine/models.py:180` `result_prompt` `max_length=20000` → `40000`（description 同步）
  - [ ] 测试：`tests/test_higgsfield_p0.py` `TestModelsBoundary` 20000/20001 → 40000/40001（max_length + feedback 两处）

## - [ ] 注释与文档同步
  - [ ] `video_prompt_engine/llm/base.py` / `prompt_engine_core/llm.py` 「≤20000 字符」注释 → 40000
  - [ ] `openspec/specs/video-prompt-engine/spec.md`「max_length 上限支持至 20,000 字符」→ 40,000
  - [ ] `CHANGELOG.md` 置顶条目

## - [ ] 门禁与交付
  - [ ] 定向 pytest（test_higgsfield_p0.py + test_prompt_engine_core.py）通过
  - [ ] 全量 pytest 回归通过（CI 同口径 3.11）
  - [ ] 双模型审查（可用时）或降级主代理直审记录
  - [ ] 推送 `codex/video-maxlength-40000` → PR（目标 main）→ CI 绿 → 合并
  - [ ] openspec archive + CCG task 归档
