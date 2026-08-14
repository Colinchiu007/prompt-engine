# 8020 引擎侧落地 Higgsfield DEEP P2（语料 few-shot 资产化 + 抽卡成本模型）

## 背景
《Hell Grind》开源项目实证：4 万条批量提示词 → 精修 → 成片的 63:1 分层漏斗淘汰率，
P2 将其"廉价层大量产出 + 昂贵层少量精修"机制参数化落地到视频提示词引擎：
（1）公开语料资产化为 few-shot 种子库（无需 API 即可复现）；
（2）num_candidates 抽卡成本模型（batch 3-5 / refined 1-2 候选）；
（3）共享内核向量检索 O(n²) → 预计算索引修复（语料扩量后 119s → 17ms）。

## 目标
1. `knowledge/seed_higgsfield_prompts.json`：258 条《Hell Grind》公开语料种子
   （590 原始 → 按 prompt_text 去重；精修 106/批量 100/变体 29/资产 23；
   seedance 234 + soul_cinematic/nano_banana 等 24），层级标签 tier:refined/batch/variant/asset
2. `scripts/build_higgsfield_seeds.py`：幂等重建（确定性排序 + 去重），loader 合并加载
3. few-shot 注入预算硬化：整段 ≤ budget（6K 默认），超长条目截断注入而非丢弃，
   预算 < 单条上限时正文以预算为第二重截断下限（保证至少注入一条），条数仅由 budget 约束
4. 向量检索性能修复：预计算 df/词项计数/范数（O(total_tokens)），结果与旧算法逐位一致
5. index.json 版本化（v2 `{"version":N,"docs":[...]}`）+ 历史裸列表兼容 +
   陈旧索引启动告警（向量 < 种子条数或 schema 旧 → 提示重跑 build_knowledge_base）
6. `docs/HELLGRIND-NUM-CANDIDATES-COST-MODEL.md`：63:1 → batch 3-5 / refined 1-2 候选参数化

## 非目标
- 不追求单请求 63 候选（成本爆炸）；分层漏斗是流水线级组合
- 图片引擎（8013）不受影响（其 vector_store 为独立 sklearn 实现）
- 语料再分发许可与 slug 冲突防护等记录待后续（见 task review.md Info）

## 实现决策（Claude 评审定案，2026-08-14）
- **去重**：按 prompt_text 去重（保留首条，seq 仍按文件夹计数）；重复的 332 条为
  同 prompt 不同 job 参数的无意义变体，对 few-shot/向量检索无增量价值且稀释 IDF
- **预算语义**：`used` 计入段头 + 标题 + 围栏（docstring 与实现一致）；首条在极小预算下
  仍注入（避免整段空注入），条数上限删除（旧 3 条硬上限未文档化）
- **版本化**：`INDEX_VERSION=2`；`_load` 兼容 dict 载荷与历史裸列表（schema_version 1/2）；
  冷启动主动 `_ensure_index()`（1.5s 移到进程启动，避免首请求卡顿）
- **并发**：search 改 zip 四元组迭代（无下标交叉，并发 add/clear 不 IndexError）
- **测试**：26 项锚定（语料结构/tier/平台白名单/确定性重建、预算截断/极小预算兜底/
  条数回归、版本化读写/旧格式兼容/陈旧告警、O(n²) 等价性与重建）
