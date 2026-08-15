# video-prompt-engine Specification

## Purpose
定义独立视频提示词优化引擎的能力：与图片提示词引擎完全分离的独立服务/知识库/策略/模型；视频专属关键词库（复用 7 个开源仓库）；结构化视频提示词输出与事实保真；批量契约与 fail-closed 校验。
## Requirements
### Requirement: 独立引擎与图片引擎分离
视频提示词优化引擎 SHALL 作为独立 Python 包（`video_prompt_engine/`）与独立 REST 服务（端口 8020）运行，不得 import 图片引擎 `prompt_engine` 的 models/strategies/knowledge/cache/config 领域层；允许依赖领域无关共享内核 `prompt_engine_core`（llm 超时重试/atomic 原子写/registry 注册器/config 解析/text 工具/api 骨架/knowledge 骨架/vector_store）；图片引擎行为零回归。

#### Scenario: 独立服务端口
- **WHEN** 启动视频引擎服务
- **THEN** 监听 8020，`GET /health` 返回 ok；图片引擎（8013）不受影响

#### Scenario: 知识库隔离
- **WHEN** 视频引擎初始化 RAG 知识库
- **THEN** 使用独立持久化目录（video_prompts_db）与视频种子，不加载图片引擎 seed_prompts.json

#### Scenario: 代码零耦合
- **WHEN** 检查视频引擎源码
- **THEN** 不存在 `import prompt_engine` 引用；仅允许 `prompt_engine_core` 共享内核依赖

#### Scenario: 共享内核行为等价
- **WHEN** 视频引擎迁移 core 机械件（llm/registry/atomic/knowledge）
- **THEN** 优化行为与迁移前一致（输出字段/缓存 key/fail closed 语义），引擎测试全量通过

### Requirement: 视频平台策略注册表
视频引擎 SHALL 提供策略注册机制（@register + get_strategy，复用 `prompt_engine_core.registry`），首期覆盖 generic_video（六要素 + Fact-Fidelity）、seedance（@引用/多模态约束）等视频平台；未知平台回退 generic_video；策略输出结构化视频字段（shot/camera/motion_intensity/scene_transition/continuity_token/duration_hint）。

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

#### Scenario: 敏感键拦截
- **WHEN** context 含 api_key/secret/password 等敏感键
- **THEN** 400/422 拒绝，不随请求外发

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

### Requirement: 图片引擎能力对齐（共享内核回灌）
图片引擎 SHALL 复用 `prompt_engine_core` 的原子写与 LLM 超时重试机械件，回灌视频引擎已验证的改进（原子写 tmp+os.replace、进程锁、动态 max_tokens、<think> 剥离），领域层（models/strategies/classifier/evaluator/cache key）保持图片语义不变。

#### Scenario: 原子写回灌
- **WHEN** 图片引擎 feedback 写入种子
- **THEN** 使用临时文件 + os.replace 原子替换，进程锁保护，与视频引擎语义一致

#### Scenario: 超时重试回灌
- **WHEN** 图片引擎 LLM 调用超时或瞬时失败
- **THEN** 应用与视频引擎一致的超时/重试/动态 max_tokens 策略，图片 provider 语义（deepseek/xfyun/gemini/minimax）不变

#### Scenario: 零回归
- **WHEN** 图片引擎迁移 core 后运行全量测试
- **THEN** 全部既有测试通过，无行为变更

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

