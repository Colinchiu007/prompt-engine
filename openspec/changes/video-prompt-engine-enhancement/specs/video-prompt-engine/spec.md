# video-prompt-engine (delta) Specification

## ADDED Requirements

### Requirement: 知识库全量扩充与平台分层
视频引擎知识库 SHALL 扩充至 100+ 条种子（来源：awesome-video-prompts/awesome-seedance/awesome-seedance-2/drama-skills/seedance2-skill），按 platform 分层；检索 SHALL 支持向量相似 + 关键词命中触发兜底（命中平台种子 top_k）。

#### Scenario: 平台 few-shot
- **WHEN** 优化 platform=seedance 且知识库含 seedance 种子
- **THEN** few-shot 注入仅含 seedance（或通用）种子

#### Scenario: 关键词兜底
- **WHEN** 向量检索无命中但输入命中关键词词典（如"运镜复刻"）
- **THEN** 检索匹配平台的种子作为 few-shot

### Requirement: 结构化输出重试
视频优化 SHALL 在 LLM 结构化输出解析失败时携带"只输出严格 JSON"提示重试（≤2 次），重试耗尽才回退原文并标记。

#### Scenario: JSON 失败重试
- **WHEN** 首次输出非 JSON
- **THEN** 重试且最终输出结构化或回退原文

### Requirement: 多平台专项策略
视频引擎 SHALL 提供 veo/kling/hailuo/doubao 平台专项策略（运镜/时长/风格/中文差异），未知平台回退 generic_video。

#### Scenario: 平台策略选择
- **WHEN** platform=veo
- **THEN** 使用 veo 专项 system prompt（长镜头/真实感约束）

### Requirement: SQLite 持久缓存
视频引擎 SHALL 提供双级缓存（内存 + SQLite），key=platform|prompt|creative_level|max_length|language，命中时跳过 LLM 调用。

#### Scenario: 缓存命中
- **WHEN** 相同请求再次提交
- **THEN** 直接返回缓存结果（不调用 LLM）

### Requirement: 评估与反馈闭环
视频引擎 SHALL 提供 evaluator（保真一致性/六要素/镜头字段/长度）与 feedback（好/坏反馈沉淀入种子库）。

#### Scenario: 多候选择优
- **WHEN** num_candidates>1
- **THEN** evaluator 评分选择最优候选

#### Scenario: 反馈沉淀
- **WHEN** 用户提交正反馈
- **THEN** 该 prompt 与结果沉淀入种子库（质量分上调）

### Requirement: 中文输出支持
视频优化请求 SHALL 支持 output_language=zh（默认 en）；zh 输出保留中文主体 + 镜头术语双语；结构化字段枚举保持英文。

#### Scenario: 中文输出
- **WHEN** output_language=zh
- **THEN** optimized_prompt 为中文详细描写（含英文镜头术语标注）

### Requirement: videogen 集成切换
Multi-Publish videogen SHALL 支持配置切换至独立视频引擎（8020）；未配置或失败时回退 8013 domain=video（兼容）。

#### Scenario: 独立引擎优先
- **WHEN** VIDEO_PROMPT_PORT=8020 已配置且服务可用
- **THEN** videogen 批量优化走独立引擎（≤20、并发 8）

#### Scenario: 回退兼容
- **WHEN** 独立引擎不可用
- **THEN** 回退 8013 domain=video 分支并记录 warning
