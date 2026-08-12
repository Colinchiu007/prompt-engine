# video-prompt-engine Specification

## Purpose
定义独立视频提示词优化引擎的能力：与图片提示词引擎完全分离的独立服务/知识库/策略/模型；视频专属关键词库（复用 7 个开源仓库）；结构化视频提示词输出与事实保真；批量契约与 fail-closed 校验。
## Requirements
### Requirement: 独立引擎与图片引擎分离
视频提示词优化引擎 SHALL 作为独立 Python 包（`video_prompt_engine/`）与独立 REST 服务（端口 8020）运行，不得 import 图片引擎 `prompt_engine` 的 models/strategies/knowledge/cache/config；图片引擎行为零回归。

#### Scenario: 独立服务端口
- **WHEN** 启动视频引擎服务
- **THEN** 监听 8020，`GET /health` 返回 ok；图片引擎（8013）不受影响

#### Scenario: 知识库隔离
- **WHEN** 视频引擎初始化 RAG 知识库
- **THEN** 使用独立持久化目录（video_prompts_db）与视频种子，不加载图片引擎 seed_prompts.json

#### Scenario: 代码零耦合
- **WHEN** 检查视频引擎源码
- **THEN** 不存在 `import prompt_engine` 引用

### Requirement: 视频平台策略注册表
视频引擎 SHALL 提供策略注册机制（@register + get_strategy），首期覆盖 generic_video（六要素 + Fact-Fidelity）、seedance（@引用/多模态约束）等视频平台；未知平台回退 generic_video；策略输出结构化视频字段（shot/camera/motion_intensity/scene_transition/continuity_token/duration_hint）。

#### Scenario: 结构化输出
- **WHEN** 优化视频提示词成功
- **THEN** 返回 optimized_prompt 渲染单串 + video 结构化字段，字段越界收敛、缺失给默认

#### Scenario: 未知平台回退
- **WHEN** 请求 platform 不在注册表
- **THEN** 回退 generic_video 策略并正常优化

### Requirement: 视频关键词库
视频引擎 SHALL 内置视频关键词词典与 few-shot 种子（来源：img-prompt 视频维度标签、awesome-video-prompts 结构化提示词、seedance2-skill 平台指令、awesome-seedance 商用用例、drama-skills 分镜模板），支持关键词查询接口与输入增强。

#### Scenario: 关键词查询
- **WHEN** 调用 GET /v1/video/keywords
- **THEN** 返回按维度（镜头/运镜/光影/色彩/风格/场景/动作）组织的中英关键词

#### Scenario: few-shot 注入
- **WHEN** 优化请求命中相似视频种子
- **THEN** system prompt 注入高质量参考示例（platform 过滤，top_k 可配）

### Requirement: 批量契约与 fail-closed
批量优化 SHALL 支持单批 ≤20 条、有界并发 8、结果顺序与请求一致、逐条非空；空结果/数量不一致/error/detail 一律 fail closed，不静默绕过。

#### Scenario: 12 条单批
- **WHEN** 批量请求 12 条视频提示词
- **THEN** 单批 200、顺序一致、逐条 optimized_prompt 非空

#### Scenario: 空项拦截
- **WHEN** 任一条结果 error 或 optimized_prompt 为空
- **THEN** 该条返回失败语义（error 优先 → detail → 空串），不产出伪造结果

### Requirement: context 注入与事实保真
视频优化 SHALL 支持 context 白名单（synopsis/character/setting/character_list/full_text）注入与敏感键拦截；策略指令含 Fact-Fidelity（不得改变主体身份/时代/事件事实）。

#### Scenario: context 白名单
- **WHEN** 请求携带 context
- **THEN** 白名单键注入 system prompt，未知键忽略并 warning，敏感键拒绝/剥离

#### Scenario: 中文历史事实保真
- **WHEN** 优化描述中文历史事件的视频提示词
- **THEN** 输出保留主体/事件/时代，不改变事实

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
