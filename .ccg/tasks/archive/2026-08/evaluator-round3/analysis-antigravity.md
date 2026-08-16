# 评估器 Round3 分析 — antigravity（降级记录）

antigravity 后端不可用（`codeagent-wrapper --backend antigravity` 启动失败，exit 1；与历史记录一致，地区/账号限制），本轮分析降级为 Claude 单模型（已实测核验，非纯推理）。

依据 CCG 决策框架：「M 以上复杂度必须双模型分析+审查」——antigravity 可用性探测失败已记录，Claude 分析作为唯一模型来源；实施后审查同样先探测 antigravity，不可用则记录降级并仅以 Claude 评审。

降级不影响分析质量：Claude 在 258 语料 + golden 12 条上实跑 4 组模拟探针（sim / grad / zh / combo），关键结论均有数字支撑。
