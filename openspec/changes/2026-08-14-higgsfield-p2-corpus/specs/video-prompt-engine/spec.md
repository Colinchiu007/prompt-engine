# video-prompt-engine Specification

## Purpose
定义独立视频提示词优化引擎的能力：与图片提示词引擎领域层分离的独立服务/知识库/策略/模型，共享领域无关内核（prompt_engine_core）；视频专属关键词库；结构化视频提示词输出与事实保真；批量契约与 fail-closed 校验；Higgsfield 公开语料 few-shot 资产化与预算注入。

## ADDED Requirements
### Requirement: Higgsfield 语料资产化与预算注入
视频引擎知识库 SHALL 内置《Hell Grind》公开语料种子（`seed_higgsfield_prompts.json`，按 prompt_text 去重，层级标签 tier:refined/batch/variant/asset）；few-shot 注入段 SHALL 受预算约束（默认 6K 字符），超长条目截断注入而非丢弃，预算小于单条上限时正文以预算为第二重截断下限（保证至少注入一条），条数仅由预算约束。

#### Scenario: 语料合并加载
- **WHEN** 加载视频种子（loader extra_path 指向 higgsfield 语料）
- **THEN** 主种子与语料合并返回，显式 platform 原样保留、缺失回退 generic_video

#### Scenario: 预算截断注入
- **WHEN** few-shot 条目超 per_item_cap（5K）或超出剩余预算
- **THEN** 截取头部注入并标注 [truncated]，不整条丢弃；极小预算也保证至少注入一条

#### Scenario: 幂等重建
- **WHEN** 重跑 scripts/build_higgsfield_seeds.py
- **THEN** 产物与已提交文件逐字节一致（确定性排序 + prompt_text 去重）

### Requirement: 向量检索性能与索引版本化
视频引擎向量检索 SHALL 使用预计算索引（df/词项计数/范数）替代逐查询全库重算（O(n²)），结果与旧算法一致；index.json SHALL 版本化（v2），兼容历史裸列表格式；检索路径与关键词兜底路径 SHALL 在语料升级后保持一致（陈旧索引启动告警并提示重建）。

#### Scenario: 扩量检索性能
- **WHEN** 知识库含 700+ 条种子执行检索
- **THEN** 单查询 warm 延迟毫秒级，结果与旧算法逐位一致

#### Scenario: 陈旧索引检测
- **WHEN** 已部署 index.json 条数 < 种子条数或 schema 版本旧
- **THEN** 启动记录 warning 提示重跑 build_knowledge_base()，不静默两路径不对称

#### Scenario: 历史格式兼容
- **WHEN** 读取历史裸列表 index.json
- **THEN** 正常加载并标记 schema_version=1，检索不受影响
