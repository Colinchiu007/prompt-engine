# 真实 MiMo 测试记录（2026-08-21）

端点：`https://opencode.ai/zen/go/v1`
模型：`mimo-v2.5`
被测代码：prompt-engine `dad77df`（PR #70 合并后）经由 `OpenAICompatProvider` + `Optimizer` 完整优化流程。
Key 仅在本机内存中使用，未落盘、未入库、未出现在日志。

## 普通流水线出词

| 场景 | 输入长度 | 输出长度 | tokens | 耗时 | 触发重试 |
|---|---|---|---|---|---|
| 短中文（猫/窗台/黄昏） | 13 | 1190 | 1342 | 14.3s | 否 |
| 中中文（宋代早市） | 40 | 1139 | 1465 | 20.8s | 否 |
| 长中文（古代城门/赋税）creative=7 | 69 | 1317 | 2075 | 22.3s | 否 |
| 英文摄影式 prompt | 171 | 1049 | 1318 | 12.8s | 否 |

四条均 `error=null`，输出包含场景、光线、构图、镜头等细节，质量符合优化预期。

## Bug 精确复现与恢复

| 预算 | 首轮 content | 重试 | 最终输出长度 | tokens | 耗时 |
|---|---|---|---|---|---|
| max_tokens=64 | 非空（102 字） | 否 | 102 | 113 | 6.2s |
| max_tokens=16 | 空 + reasoning 非空 | 是（第 1 次重试） | 1207 | 485 | 15.0s |
| max_tokens=1 | 空 + 无 reasoning | 否（fail-closed） | 0 | 50 | 3.2s |

结论：

- 原问题路径「content 为空 + reasoning_content 非空」在真实 MiMo 上通过重试成功恢复，输出完整优化词。
- 正常请求不触发重试，稳定产出 1000+ 字优化词。
- max_tokens 极端到 1 且无 reasoning 时按设计 fail-closed 返回空，不伪造提示词。
