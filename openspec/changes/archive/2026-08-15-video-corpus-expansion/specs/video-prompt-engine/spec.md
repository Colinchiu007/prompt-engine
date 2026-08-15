## ADDED Requirements

### Requirement: 语料目录规范与格式扩展
视频引擎语料 SHALL 支持目录化组织（`knowledge/corpus/<source>/`，构建脚本 glob 合并）与条目格式扩展：可选字段 `corpus_type`（positive/negative，默认 positive）、`failure_tags`（负样本失败模式标签，对齐 failure_patterns.json）、`applicable_to`（few-shot/eval/both，默认 few-shot）；旧条目无新字段时行为零回归。

#### Scenario: 目录合并加载
- **WHEN** `knowledge/corpus/` 下新增语料 JSON
- **THEN** 构建脚本合并加载，loader 输出包含新条目，既有主种子/语料文件不受影响

#### Scenario: 旧格式兼容
- **WHEN** 语料条目不含 corpus_type/failure_tags/applicable_to
- **THEN** 按 positive + few-shot 语义处理，加载与检索行为不变

### Requirement: 负样本资产与 few-shot 排除
视频引擎 SHALL 提供负样本语料资产（`seed_failure_samples.json`，批量抽卡层失败样本 + 失败模式标签）；`corpus_type=negative` 或 `applicable_to` 不含 `few-shot` 的条目 SHALL 不进入 few-shot 注入段（防污染生成参考），但 SHALL 可供评估/规则校验使用。

#### Scenario: 负样本不进 few-shot
- **WHEN** 检索命中 `corpus_type=negative` 条目
- **THEN** few-shot 注入段不含该条目，向量/关键词检索路径仍可单独访问

#### Scenario: 正样本正常注入
- **WHEN** 检索命中 `corpus_type=positive` 且 applicable_to 含 few-shot 的条目
- **THEN** 正常注入 few-shot 段（受预算约束）

### Requirement: 负样本规则命中率校验模式
视频引擎 evaluator SHALL 支持负样本校验入口：对 `seed_failure_samples.json` 逐条评估，统计违规扣分规则对预期 `failure_tags` 的命中率（召回），输出汇总（命中/漏检/误报）；该模式不影响既有评分路径，用于规则阈值校准与回归保护。

#### Scenario: 规则召回统计
- **WHEN** 对负样本执行校验模式
- **THEN** 返回每类失败模式的命中率/漏检数，且不改变常规 evaluate() 输出

#### Scenario: 常规评分零影响
- **WHEN** 未启用负样本校验模式
- **THEN** 既有 evaluate/select_best 行为完全不变

### Requirement: 语料校验门禁
视频引擎语料构建/加载 SHALL 校验：必填字段（id/prompt_text/language/tier 分类）、prompt_text 长度下限、tier 合法值（refined/batch/variant/asset）、prompt_text 重复、quality_score 范围（0-10）；非法条目按可配置策略 fail-closed 或带 warning 跳过，且不静默混入。

#### Scenario: 非法条目拦截
- **WHEN** 语料条目缺必填字段或 prompt_text 过短
- **THEN** 构建失败或该条目带 warning 跳过（按配置），不产生半成品索引

#### Scenario: 重复检测
- **WHEN** 新语料 prompt_text 与既有条目重复
- **THEN** 按确定性规则保留一条并记录去重数（与 Higgsfield 语料去重语义一致）
