# 抽卡成本模型 — num_candidates 建议值推导（DEEP P2.10）

> 来源：《Hell Grind》开源项目实证（63:1 抽卡淘汰率）→ 视频提示词优化引擎多候选评估的成本-收益参数化。
> 关联：`video_prompt_engine/optimizer.py`（多候选择优）、`models.py`（`num_candidates` 字段 ge=1 le=5）。

## 1. 为什么 63:1 不等于"生成 63 个候选"

Hell Grind 的 63:1 是**流水线级**淘汰率：4 万条批量提示词 → 精修 → 成片，每一层都在筛。
它不是"同一个请求生成 63 个候选"，而是"廉价层大量产出 + 昂贵层少量精修"的分层漏斗。

引擎对应关系：

| Higgsfield 流水线 | 引擎机制 | 成本特征 |
|---|---|---|
| 批量抽卡层（2-3KB 模板，大量产出） | `creative_level` 低 → batch 形态 | 单候选 token 成本低 |
| 精修层（21-27KB 导演分镜单，少量） | `creative_level` 高 → refined 形态 | 单候选 token 成本高 10 倍 |
| 63:1 淘汰 | `evaluator` 多候选择优 + 违规扣分 | 评估开销随候选数线性增长 |

## 2. 收益模型

假设单候选达到"可用"质量阈值的概率为 p（相互独立，实际因同源 system prompt 呈正相关，见 §4）：

```
P(至少一个可用 | n 个候选) = 1 - (1 - p)^n
```

| p | n=1 | n=2 | n=3 | n=5 |
|---|---|---|---|---|
| 0.2 | 20% | 36% | 49% | 67% |
| 0.3 | 30% | 51% | 66% | 83% |
| 0.4 | 40% | 64% | 78% | 92% |

边际收益随 n 递减：2→3 提升约 +15pp，3→5 提升约 +18pp（p=0.3 时）。

## 3. 成本模型与建议值

```
单请求成本 ≈ num_candidates × (system+prompt 输入 tokens + 输出 tokens) × 单价
            + num_candidates × evaluator 评估开销
```

建议值（默认仍为 1，按 tier 显式上调）：

| 形态 | 建议 num_candidates | 理由 |
|---|---|---|
| batch（creative_level 低） | **3~5** | 单候选 1-2K tokens，成本低；多候选显著提升"找出高分变体"概率 |
| refined（creative_level 高） | **1~2** | 单候选 20K+ tokens，成本高 10 倍；evaluator 违规扣分已保证结构质量门槛，多候选边际收益低 |

成本护栏：refined 形态建议预算 ≤ 3× 单候选成本（即 num_candidates ≤ 2-3），
超出部分建议转投"批量层多抽 + 精修层单次"的流水线组合（对应 Higgsfield 分层漏斗）。

## 4. 已知限制

- **候选相关性**：候选来自同一 system prompt + 同一输入，错误模式高度相关（如都缺 Audio 块），
  实际收益低于独立假设；`temperature` 固定时相关性更高。
- **评估噪声**：evaluator 评分为启发式（保真/六要素/长度/结构），非真值；多候选择优可能放大评估器偏好。
- **缓存**：缓存 key 含 `num_candidates`，不同候选数不共享缓存（有意为之，防低候选数结果污染高候选数请求）。
- **63:1 的正确打开方式**：引擎不追求单次 63 候选（成本爆炸），而是 batch 层 3-5 候选 + refined 层 1-2 候选 +
  evaluator 违规扣分的分层漏斗——与 Higgsfield 流水线同构。

## 5. 实施状态

- [x] `num_candidates` 参数化：`models.py` 字段（ge=1, le=5），多候选择优已实现（`optimizer.py`）
- [x] evaluator 违规扣分 + 层级长度（DEEP P0.1，`evaluator.py`）
- [x] 分层漏斗机制（batch/refined 形态，DEEP P1.5，`strategies/generic_video.py` tier）
- [ ] 默认值策略：保持默认 1；建议调用方按 tier 显式传入（batch 3-5 / refined 1-2）