# 设计：max_length 边界上浮 40000

## 决策

- **只动校验边界，不动默认与预算逻辑**：`VideoOptimizeRequest.max_length` 是 Pydantic 校验上界（`le`）。放开到 40000 后，契约层显式 `max_length=40000` 不再 422；真实 LLM 输出仍受 `llm.max_tokens_cap`（默认 16384）约束——`max(3000, (max_length or 1800) * 2)` 在 40000 时 = 80000，被 `min(_, cap or 16384)` 压回 16384，不会触发 OpenAI 兼容端点 400（W1 既有防线）。
- **feedback `result_prompt` 同步**：沿用 5000→20000 的同步先例（CHANGELOG「feedback result_prompt 上限同步 20000」）。精修层输出可能超过 20000 字符时，坏评回传 `result_prompt` 若仍 `le=20000` 会 422，反馈闭环断裂。同步到 40000 保持「引擎输出可回传」。
- **评估器独立 API 不动**：`VideoEvaluateRequest.max_length`（`le=20000`）是 `/v1/video/evaluate` 的评测预算参数，桌面契约不调用；optimizer 内部 `evaluate()` 是普通函数（`optimizer.py:337` 直传 `request.max_length`，不经 Pydantic），40000 不会在精修层内部 422。独立 API 语义不属于本次放宽面，保持不动避免扩大范围。
- **评论性注释同步**：llm 两处「≤20000 字符」描述改为 40000，防止文档与校验边界漂移。

## 数据流

契约层 `optimizeVideoPrompt(..., max_length: 40000)` → `POST /v1/video/optimize`（或 batch）→ Pydantic 校验 `le=40000` 通过 → tier 判定（creative_level≥7 → refined）→ `provider.call(max_length=40000)` → `max_tokens=min(80000, 16384)=16384` → 长模板输出完整生成 → `evaluate(..., max_length=40000)`（普通函数，无校验）→ 落库（桌面侧 safeText 上限同步 40000）。
