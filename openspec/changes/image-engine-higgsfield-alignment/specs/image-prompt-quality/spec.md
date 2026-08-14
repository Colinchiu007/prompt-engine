## Purpose

定义图片提示词引擎的质量评估与多候选择优行为：在候选生成后以确定性启发式评分择优，并对缺席角色、角色替换类违规扣分，同时按创意层级（batch/refined）采用不同的长度判据。该能力从视频引擎（8020）已验证的 Higgsfield 机制移植，按图片领域适配。

## ADDED Requirements

### Requirement: 多候选择优

当请求的 `num_candidates` 大于 1 时，引擎 SHALL 以确定性质量评分对全部候选排序，将最高分候选作为主输出（`optimized_prompt`），并按分数降序返回候选列表。单候选请求 MUST 保持原路径行为不变（不引入评分开销、输出与既有一致）。

#### Scenario: 多候选按分数降序择优
- **WHEN** 请求 `num_candidates=3` 且三个候选的评分分别为 72、88、65
- **THEN** `optimized_prompt` 为评分 88 的候选，候选列表按 88、72、65 降序返回

#### Scenario: 单候选零变化
- **WHEN** 请求 `num_candidates=1`
- **THEN** 输出与既有单候选路径完全一致，不执行择优评分

### Requirement: 确定性质量评分

评分 SHALL 为确定性启发式计算（不调用 LLM、不引入随机性），综合：六要素命中（主体/动作/环境/光影/色彩/风格）、层级长度判据、源提示词保真度，并叠加违规扣分。相同输入 MUST 得到相同评分；评分范围为 0-100（含扣分后的下限 0）。

#### Scenario: 评分可复现
- **WHEN** 对同一候选与同一源提示词连续评估两次
- **THEN** 两次评分完全一致，且全程无 LLM 调用

#### Scenario: 评分带违规扣分
- **WHEN** 候选文本包含已声明缺席的角色名
- **THEN** 最终评分在基础分上扣除 10 分，且结果中暴露违规明细（命中项）

### Requirement: 违规扣分（缺席角色与角色替换）

当请求声明 `excluded_characters`（缺席角色）时，候选文本包含任一缺席角色名 SHALL 扣 10 分；当声明 `no_swap_pairs`（禁止替换对）时，候选文本包含任一替换源角色名 SHALL 扣 10 分。字段未声明或为空时 MUST NOT 扣分。引用协议标记（`[ABSENT]`、`<<<...>>>`）区段 SHALL 在匹配前剥离，避免合规输出自罚分。图片领域无尾行与音频概念，`missing_trailer` / `missing_audio` 类违规 MUST NOT 适用于图片评分。

#### Scenario: 缺席角色命中扣分
- **WHEN** 请求声明 `excluded_characters=["JAX"]` 且候选文本正文包含 "JAX"
- **THEN** 评分扣除 10 分并记录命中项

#### Scenario: 未声明字段不扣分
- **WHEN** 请求未声明 `excluded_characters` 与 `no_swap_pairs`
- **THEN** 候选文本包含任意角色名也不触发扣分

#### Scenario: 引用标记不自罚
- **WHEN** 候选文本仅在 `[ABSENT] JAX` 或 `<<<JAX>>>` 标记中出现角色名、正文未出现
- **THEN** 不触发缺席角色扣分

#### Scenario: 替换源命中扣分
- **WHEN** 请求声明 `no_swap_pairs=[["ROKO","JAX"]]` 且候选文本正文包含 "ROKO"
- **THEN** 评分扣除 10 分并记录命中对

### Requirement: 创意层级长度判据

引擎 SHALL 按创意层级采用不同长度判据：`creative_level >= 7` 判定为 refined 层，否则为 batch 层。batch 层与 refined 层 MUST 使用各自的词数（英文）或字符数（中文）上下界；上界 MUST 与请求 `max_length` 联动且设置封顶，防止预算放大时判据静默扩张；refined 层下界 MUST 在小预算下自适应收缩（防区间坍缩）。长度判据仅用于评分与择优，MUST NOT 截断或改写候选文本。

#### Scenario: refined 长提示词不被 batch 判据误杀
- **WHEN** `creative_level=8`、`max_length=2000` 且候选为 800 词的详细描述
- **THEN** 按 refined 层判据长度合规（不因超出 batch 上界扣分）

#### Scenario: 小预算下 refined 下界自适应
- **WHEN** `creative_level=8`、`max_length=300`（约 60 词预算）
- **THEN** refined 下界按预算收缩，60 词级候选不因低于固定下界被误判

#### Scenario: 上界封顶
- **WHEN** 请求 `max_length` 为上限 2000 且 batch 层
- **THEN** batch 上界不超过封顶值，不随预算继续放大

### Requirement: 双向约束字段契约

`OptimizeRequest` SHALL 接受可选字段 `excluded_characters`（字符串数组）与 `no_swap_pairs`（二元字符串数组的数组，每对恰含两个非空字符串）。非法形态（非数组、元素非字符串、对长不为 2）SHALL 在 API 边界丢弃并记录警告，MUST NOT 抛错中断请求；超长列表 SHALL 截断至上限（excluded ≤ 20 项、no_swap_pairs ≤ 10 对）。字段缺省时引擎行为 MUST 与既有版本一致。

#### Scenario: 合法字段生效
- **WHEN** 请求携带 `excluded_characters=["JAX"]` 与 `no_swap_pairs=[["ROKO","JAX"]]`
- **THEN** 字段进入评分流程并正常参与违规扣分

#### Scenario: 非法形态丢弃
- **WHEN** 请求携带 `excluded_characters="JAX"`（字符串而非数组）
- **THEN** 该字段被丢弃并记录警告，请求正常完成且不扣分

### Requirement: 既有能力兼容

图片引擎既有的 LLM 对比评估（compare 模式 5 维 before/after）SHALL 保持不变；经 `prompt_engine` 的视频领域 legacy 路径行为 MUST NOT 因本能力改变；新字段缺省时，既有测试基线 MUST 全部通过。

#### Scenario: compare 模式不受影响
- **WHEN** 调用既有 compare 评估接口
- **THEN** 返回 5 维 before/after 评分，格式与既有一致

#### Scenario: 视频 legacy 路径不变
- **WHEN** `domain=video` 经 `prompt_engine` 优化且未声明新字段
- **THEN** 输出与既有版本一致，不应用图片违规扣分
