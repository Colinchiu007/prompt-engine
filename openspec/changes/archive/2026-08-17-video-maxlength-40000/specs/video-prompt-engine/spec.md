## MODIFIED Requirements

### Requirement: 精修层长度词数刻度

视频引擎 refined 层长度判据 SHALL 使用词数刻度 500–5,000 词（max_length 为输出裁剪预算，不参与 refined 上界判据）；`VideoOptimizeRequest.max_length` 校验上界 SHALL 支持至 40,000 字符（2026-08-16 由 20,000 上浮，容纳真实导演分镜单形态）；batch 上界封顶 833 词；`VideoFeedbackRequest.result_prompt` 上限 SHALL 同步 40,000（精修层长结果可回传）；`VideoEvaluateRequest.max_length`（独立评测预算）保持 le=20000 不变。

#### Scenario: 40000 接受 / 40001 拒绝

- **WHEN** 请求携带 `max_length=40000`
- **THEN** 校验通过，进入优化流程（refined 层长模板可完整生成；max_tokens 仍受默认 cap 16384 约束）
- **AND WHEN** 请求携带 `max_length=40001`
- **THEN** 校验拒绝（422/ValidationError）

#### Scenario: feedback 40000 字符结果回传

- **WHEN** 用户对 40000 字符内的引擎输出提交反馈
- **THEN** `result_prompt` 校验通过；40001 字符拒绝

#### Scenario: 默认与预算语义不放松

- **WHEN** 未显式携带 `max_length` 或携带 20000 及以下值
- **THEN** 行为与上界 20000 时一致（默认 1800、tier 默认、独立评测预算 le=20000、max_tokens cap 16384 不变）

#### Scenario: 长分镜单不误杀

- **WHEN** refined 模板 1,000-5,000 词
- **THEN** 长度判据通过

#### Scenario: 超长拒绝

- **WHEN** 词数 >5,000
- **THEN** 长度判据失败
