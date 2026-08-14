# 评审记录 — image-engine-higgsfield-alignment

日期：2026-08-14
方式：双模型评审降级（antigravity 地区不可用 → Claude wrapper 本轮无响应被终止 → 主代理自查 + 既有基线测试锚定）
状态：0 Critical / 0 Major / 2 Info

## 评审关注点自查

| 关注点 | 结论 | 依据 |
|---|---|---|
| 评分公式权重 | OK：length20+elements30+fidelity20，/0.7 归一（图片无镜头字段），violations 叠加后 clamp 0-100 | evaluator.py evaluate_quality；test_score_range_and_penalty_floor |
| 违规匹配正确性 | OK：词边界/整名（单字符拒绝防"关"误击"关键"）；标记剥离只剥标记+紧邻一词，同句真实出现仍命中 | test_word_boundary_chinese_no_false_positive / test_marker_real_appearance_still_hits |
| rest 收敛安全 | OK：非法形态丢弃+warning 不抛错；字符串兼容分割；去重；超限截断 20/10；模型字段 Optional[Any] 避免 Pydantic 422 拦截 | test_string_form_split / test_invalid_form_discarded / test_oversize_truncated |
| 择优回归风险 | OK：单候选（num=1）不接入评分；视频 legacy（is_video）不接入；缓存 key 已含 num_candidates；失败路径外层 try/except 兜底 | test_num1_unchanged / test_video_legacy_unchanged |
| spec 场景覆盖 | 全场景有测试映射：择优排序/单候选零变化/确定性/违规明细/未声明不扣/标记不自罚/替换源命中/refined 长提示词/小预算自适应/上界封顶/compare 回归/视频 legacy | tests/test_image_higgsfield_alignment.py 35 项 |

## Info 级（不阻塞，记录备查）

- I1：evaluate_quality 直接调用方若把 excluded_characters 传字符串（绕过 rest），_contains_word 按整串匹配会失效——optimizer 已防御（isinstance str → [str]），契约文档注明 meta 应为 list（与视频引擎一致）。
- I2：rest 层原地修改请求对象后交 asyncio.to_thread——请求对象不再共享，线程安全。

## 测试证据

- 新测试 35/35 通过（tests/test_image_higgsfield_alignment.py）
- 相关模块回归 73/73（optimizer/evaluator/api_endpoints/compare_api）
- 全量 688 passed / 3 skipped / 1 deselected（rag_cases 既有环境失败，stash 验证与本次无关）/ 5 web E2E errors（需本地 server，环境类）


## CI 修复补充（2026-08-14，PR #45 首轮 CI 失败）

- 失败项：test (3.11) → tests/test_ab.py::TestABCandidates::test_optimize_multiple_candidates
- 根因：旧断言按「调用顺序」期望 candidates[0..2] == Version A/B/C；新择优实现按 evaluate_quality 分数降序排列（design 风险 R2 标注的预期收益），Version C 分数最高排首位。
- 修复：断言改为「择优不变量」——主输出 == candidates[0] + 分数降序（post_process 关键词注入带随机性，固定顺序断言不成立）；tokens_used 断言保留。
- 结论：生产代码无缺陷，属测试套件与预期行为对齐。


## 2026-08-14 追加：PR #45 CI 修复与合并
- 修复 commit 470a676：`tests/test_ab.py` 断言改为择优不变量（主输出 == candidates[0] + 分数降序）；根因为新择优实现按 evaluate_quality 分数排序，旧断言按调用顺序期待。生产代码无缺陷。
- PR #45 已合并（squash，2026-08-14T12:15:41Z）；openspec change 已归档。
