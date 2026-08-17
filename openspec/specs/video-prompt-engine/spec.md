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

### Requirement: 跨镜承接保真（continuity_check）
视频引擎 SHALL 支持跨镜承接检查：`prev_final_frame`（≤1000 字符）承载上一镜终态描述，注入 SCENE Continuity 事实引用段；V4 缓存盐 SHALL 加入终态 SHA-1 前缀哈希（承接状态变化缓存必然失效）；无 `prev_final_frame` 时零回归。

#### Scenario: 英文承接命中
- **WHEN** 英文 prompt 共享实体命中率 ≥40% 且终态帧实际出现的角色名（character_list 白名单）硬命中
- **THEN** 承接判定通过；未达阈值记 continuity_break -5

#### Scenario: 中文承接命中
- **WHEN** 中文终态白名单词（角色名+姿势/位置词）重合 ≥60%，或白名单为空时最长公共子串覆盖率 ≥0.5
- **THEN** 承接判定通过；未达阈值记 continuity_break -5

### Requirement: 导演分镜块骨架与块覆盖
视频引擎 refined 层 SHALL 使用《Hell Grind》语料统计的 12 块顺序渲染骨架（SCENE NOTE → SPATIAL LAYOUT → LIGHTING → COLOR → CAMERA → ENVIRONMENT → CONTINUITY → CHARACTERS → SKIN → ACTING → STILLNESS LOCK → FINAL FRAME）；`blocks` 12 键白名单（每键 ≤4000 字符）；块覆盖度 SHALL 按渲染串命中块标记比例判定（min_ratio=0.8，分母=meta.blocks 非空块数）。

#### Scenario: 块覆盖达标
- **WHEN** refined 渲染串命中块标记比例 ≥0.8
- **THEN** block_coverage 通过，不扣分

#### Scenario: 块覆盖不足
- **WHEN** 命中比例 <0.8
- **THEN** 记 block_coverage -5

### Requirement: lock-trigger gated 规则（否定感知）
视频引擎 SHALL 提供 lock-gated 启发式规则：默认启用 dead_center / exposure_break / eye_line 三条，仅当 lock 词真实（非否定）出现时检测 forbidden 词；规则资产（refined_blocks.json）缺失/损坏时回退空表（规则不启用零误报）；命中记 -5。

#### Scenario: 否定前缀不误伤
- **WHEN** 正文含 "keep the hero OUT of the center of frame" 等否定禁令形态
- **THEN** 不记 lock 违规

#### Scenario: 资产缺失零误报
- **WHEN** refined_blocks.json 缺失或损坏
- **THEN** gated 规则不启用，评估正常完成

### Requirement: 精修层长度词数刻度
视频引擎 refined 层长度判据 SHALL 使用词数刻度 500–5,000 词（max_length 为输出裁剪预算，不参与 refined 上界判据）；`max_length` 上限 SHALL 支持至 40,000 字符（容纳真实导演分镜单形态，2026-08-16 由 20,000 上浮）；batch 上界封顶 833 词。

#### Scenario: 长分镜单不误杀
- **WHEN** refined 模板 1,000-5,000 词
- **THEN** 长度判据通过

#### Scenario: 超长拒绝
- **WHEN** 词数 >5,000
- **THEN** 长度判据失败

### Requirement: 输出语言按平台路由
视频引擎输出语言 SHALL 按「显式参数 → 目标平台集合 → model 关键词兜底 → 文本 CJK 检测」解析；国产视频模型（minimax/seedance/kling/hailuo/doubao/cogvideo/hunyuan/wan/agnes）默认 zh，国外模型（veo/runway/sora/ltx/pika/luma）默认 en，避免中文提示词错配国外模型。

#### Scenario: veo 英文优先
- **WHEN** platform=veo 且未显式指定语言
- **THEN** 输出语言路由为 en

#### Scenario: seedance 中文优先
- **WHEN** platform=seedance 且未显式指定语言
- **THEN** 输出语言路由为 zh

### Requirement: 策略约束增强
视频引擎策略 SHALL 支持：lens discipline（character lock / STRICT block / final frame / plausible negative）、文化/族裔锚定（角色外貌与文化背景一致）、Zero Text Artifacts（禁止画面内文字伪影）三类硬约束；相应约束进入系统提示词并随平台策略生效。

#### Scenario: 无文字约束
- **WHEN** 优化视频提示词
- **THEN** system prompt 含 Zero Text Artifacts 强制约束

#### Scenario: 文化锚定
- **WHEN** 角色描述含族裔/文化背景
- **THEN** 优化结果保持外貌与文化背景锚定，不漂移
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
### Requirement: 评估器 P0-P2 优化（tier/form/保真/运镜/区分度/词表资产）
视频引擎 evaluator SHALL 支持：tier 白名单含 asset/variant 且 auto 判定增加 >833 词→refined 长度兜底；`checks["form"]` 形态标签（<100 词推断 asset）；长度带按 tier 分带（batch/refined/asset/variant，en 词数 / zh 字符），`length_strict=False` 评测口径按接近度梯度给 0-20 分、True 引擎候选口径 0/20 二值；英文保真用实体 token 词边界命中率（无实体→1.0 不扣分）；运镜词表只保留镜头运动词（walking/running/moving 不计运镜）；六要素支持部分命中（score=min(1, 命中词数/3)）并保留布尔 `elements` 兼容键；六要素关键词 SHALL 外置为共享资产 `prompt_engine_core/knowledge/element_keywords.json`（en/zh/ru，缺失/损坏回退内置默认），视频与图片评估器共用；`select_best` 同分时违规数少者胜；`evaluate_negatives` FP 按样本×违规键去重归属；`evaluate()` 返回纯规则 `advice`（中英双语，可关闭）。

#### Scenario: 纯文本长片不再误分层
- **WHEN** 输入 900 词无引擎标记的纯文本
- **THEN** auto tier 判为 refined，长度按 500-5000 词带判定

#### Scenario: 短资产卡形态
- **WHEN** 输入 <100 词文本且未显式指定 tier
- **THEN** checks["form"]=asset（形态标签），长度带仍按 auto tier（batch）判定；显式 tier=asset 才启用 20-950 词带

#### Scenario: 评测口径长度梯度
- **WHEN** length_strict=False 且长度带外
- **THEN** 长度分按接近度 0-20 部分给分，违规列表不含长度

#### Scenario: 主体运动不认运镜
- **WHEN** 正文仅含 walking/running/moving 等主体运动词
- **THEN** has_motion=False；含 pan/dolly/crane/运镜 等镜头运动词才为 True

#### Scenario: 词表资产共享
- **WHEN** 图片与视频评估器加载六要素关键词
- **THEN** 均来自 element_keywords.json（任一语言命中即算），图片引擎自动获得扩充词

#### Scenario: 建议输出
- **WHEN** evaluate() 带 enable_advice=True
- **THEN** 返回 advice 列表（长度/要素/镜头/违规逐条，zh 或 en），enable_advice=False 时为空列表

### Requirement: 确定性评测端点与 golden set
视频引擎 REST SHALL 提供 `POST /v1/video/evaluate`：1-20 条纯文本逐条确定性评分（无 LLM），支持可选 `compare` 逐条 before/after 双路对比（score_delta + by_criterion 判据 delta（长度/六要素/镜头/保真/违规））、显式 tier/language/max_length/length_strict/detail；prompts 每条非空、compare 长度不一致返回 422。评测器校准 SHALL 提供 golden set 资产（`knowledge/golden_set.json`，含人工分/理由/来源）与 `scripts/eval_golden_set.py`（MAE/RMSE/Pearson r + 逐条对比，退出码 0）；golden 资产不进入 few-shot 注入。

#### Scenario: 双路对比
- **WHEN** 提交 prompts 与等长 compare 数组
- **THEN** 每条返回 score_before/score_delta/by_criterion（六要素/镜头/保真/违规 delta）

#### Scenario: 参数校验
- **WHEN** prompts 含空条目、超过 20 条或 compare 长度不匹配
- **THEN** 返回 422

#### Scenario: golden set 校准
- **WHEN** 运行 scripts/eval_golden_set.py
- **THEN** 输出评估器分 vs 人工分 MAE/RMSE/Pearson r 与逐条对比表，退出码 0

### Requirement: 评估器深水区优化 round2（跨语言保真/中文名字边界/违规量化/阈值联动/版本指纹/语料门禁）
视频引擎 evaluator SHALL 支持：`evaluator_version`（v0.11-deterministic）与 `assets`（element_keywords/refined_blocks/golden_set sha256）版本指纹随 evaluate() 返回；`checks["violations_detail"]` 违规分级量化（顶层 `violations` 保持 dict[str,int] 计分兼容；timing_break 带 count+max_diff/total_diff，block_coverage 带 hit/total/ratio）；跨语言保真门控（source 与 prompt 一侧含 CJK 另一侧不含时启用 `fidelity_method=cross_lingual`：0.5 要素跨语言守恒 + 0.3 镜头结构保留 + 0.2 长度比（CJK 按汉字数），要素守恒与镜头结构按 zh→en/en→zh 双向配对计分，en→en/zh→zh 路径零触碰）；中文保真 2-gram 归一（`_zh_fidelity_grams` 去高频虚字后取二元组）；角色名匹配走 `_contains_name`（拉丁词边界；CJK 长名覆盖守卫 known_names=excluded+swap+character_list 并集，2 字 token 后随字白名单仅含纯功能字（动词/助词/介词/方位，剔除常用名字尾字）防「林晓」误击「林晓雨」；泛词路径维持子串）；[ABSENT] 标记豁免的剥离与识别共用 known_names 并集（覆盖 character_list roster 角色，拉丁名后随边界 + 同位置长名覆盖去重）；六要素拉丁词词边界命中（CJK 子串；西里尔左侧词边界防 фон 误击 телефон/микрофон，右侧容忍变格；复数 -s/-es 容错）；batch 长度上界与 refined 长度兜底阈值单一来源 `_batch_hi`（400-833 联动，长度兜底推断 refined 时豁免 missing_trailer，`checks["tier_auto"]` 输出推断来源）；RU 与 zh 同按字符刻度长度带；空输入显式 0 分契约（checks 形状与正常路径对齐，advice 按 language）；advice 按违规惩罚绝对值降序；`select_best(detail=False)` 扩展 4 元组（候选含 checks/violations/advice，默认 3 元组不变）；tie-break 改总惩罚量 `sum(abs(penalty))`（1 个 -10 与 2 个 -5 惩罚量相等并列，稳定排序）；RU 词表补齐（subject/color/environment，资产 version 2，knowledge.py fallback 同步）；golden set 校准门禁（MAE≤18 / Pearson r≥0.90）与 258 语料复测哨兵（mean 跌幅 ≤2.0、≥90 占比跌幅 ≤5pp）。

#### Scenario: 中文名字边界
- **WHEN** excluded 角色「林晓」而正文为「林晓雨站在门口」，或 character_list 含「林晓雨」
- **THEN** 不触发 excluded_present（长名覆盖/后随字白名单）；正文「林晓走进房间」仍命中

#### Scenario: 跨语言保真门控
- **WHEN** source 为中文、prompt 为英文忠实翻译（要素/镜头/长度守恒），或反之 en→zh
- **THEN** fidelity_method=cross_lingual 且 fidelity≥0.7（双向配对计分）；en→en/zh→zh 路径 fidelity_method 保持 wordlist/zh2gram

#### Scenario: [ABSENT] 豁免覆盖 roster 角色
- **WHEN** 正文含 `<<<[ABSENT] Roko>>>` 且 character_list=["Roko"]、prev_final_frame 含 Roko
- **THEN** 不触发 continuity_break（豁免来自 [ABSENT] 判定而非标记残留）；无标记时缺席仍判 continuity_break

#### Scenario: 阈值单一来源与豁免
- **WHEN** 无引擎标记纯文本 400-833 词 auto tier 判 refined（tier_auto=length）
- **THEN** 长度带按 refined 判定且 missing_trailer 不扣分

#### Scenario: 版本指纹
- **WHEN** 调用 evaluate() 或 POST /v1/video/evaluate
- **THEN** 返回 evaluator_version 与 assets sha256；REST meta.evaluator 与引擎常量一致

#### Scenario: golden 门禁与语料哨兵
- **WHEN** 运行 scripts/eval_golden_set.py 与 258 语料复测
- **THEN** golden MAE≤18 且 Pearson r≥0.90；258 mean 跌幅 ≤2.0 且 ≥90 占比跌幅 ≤5pp

### Requirement: 评估器 round3（zh/ru 长度兜底/CJK 合成词词表/258 哨兵门禁/正则缓存/镜头分型 instrumentation/无 source 缩放封顶）
视频引擎 evaluator SHALL 支持：`detect_tier` 语言感知长度兜底（`language` 参数默认 en 向后兼容；入口归一化 `zh-CN→zh`/`EN→en`，zh/ru 按字符刻度 `len(prompt)>_CHAR_BATCH_HI → refined`，阈值与 zh/ru batch 带上界共用 `_CHAR_BATCH_HI=2000` 单一来源，length_fallback/tier_auto/trailer_waiver 三处同步，缺失时 3000 字中文转 refined 不产生 missing_trailer 误伤）；refined/batch 音频意图词统一单表 `_AUDIO_INTENT_WORDS`（en dialogue/voiceover/narration/vocal + zh 音效/配乐/对话/旁白/音乐/背景音乐/环境声/雨声/风声/枪声 + ru звук/музыка/речь/голос/диалог/эффект，消除双表漂移）；zh 六要素词表 v4（去全部单字补合成词，subject 保留「人」为刻意例外，v4 补高频动作形态 走着/跑来/挥手/望着/坐着/看着 等，资产 version 4 随 `_asset_fingerprint` 自动反映）；镜头/机位/运动分型 instrumentation（`checks.shot_types/camera_types/motion_types` + `*_count`，保守词表禁裸 still/extreme/摇，裸 wide/aerial 保留为景别核心词，运镜型归 motion 不归 shot（tracking/dolly/跟拍/推移 为景别-运镜双属特例），否定感知按分句全出现语义（复用 `_occurrence_is_negated`，与 `_negated` 一致），零分数影响）；`_WORD_BOUNDARY_RE`/`_CYRILLIC_BOUNDARY_RE` lru_cache(2048) 正则缓存（键仅 token、线程安全、maxsize 防跨镜承接/角色名等动态 token 无界膨胀，淘汰后重编译正确性不变）；无 source 缩放封顶 `score = min(score, 90 + 7*elements_score)`（≤97，100 保留给「source 保真已验证」独占空间，有 source 不封顶，elements_score 双重使用于 docstring 注明）；258 语料哨兵门禁 `scripts/eval_corpus_258.py`（固定路径读种子文件并断言 total==258，三路语言判定复用 `detect_lang` 共享 util（CJK→zh/西里尔→ru/else en），`--json`，退出码 0/1/2（输入损坏也返回 2），CI 独立 step timeout 10 分钟（job 级 15 分钟预算），门禁 mean≥88.0/ge90≥190/lt60≤30/missing_audio≤40 先宽后紧）；`/v1/video/evaluate` 未显式传 language 时逐条自动判定（同一 `detect_lang` 口径）；`evaluator_version` 升 v0.12-deterministic。

#### Scenario: zh/ru 字符刻度长度兜底
- **WHEN** 无引擎标记中文 2500 字且 language=zh（或俄语 2500 字 language=ru）
- **THEN** detect_tier 判 refined、tier_auto=length、missing_trailer 豁免；1900 字仍判 batch；en 默认路径词数兜底行为不变

#### Scenario: CJK 合成词词表
- **WHEN** 正文含 角色/曝光/时光/金属/战术/中景/远景
- **THEN** color/lighting/color/color/action/environment/environment 均不命中；红色/奔跑/室内/灯光/将军 仍命中；subject「人」例外保留（四个人）；v4 动作形态 将军走着/小孩跑来/挥手告别 命中 action（走着/跑来/挥手）

#### Scenario: 镜头分型 instrumentation
- **WHEN** 正文含 "Wide close-up of a man"、"no rotation, camera static"、"slow pan with zoom"
- **THEN** shot_types=[wide,closeup]/count 2；motion_types 不含 rotate（否定感知）而含 pan/zoom；has_shot 等既有布尔计分不变（零分数影响）

#### Scenario: 无 source 缩放封顶
- **WHEN** 无 source 且六要素全中（elements_score=1.0）
- **THEN** score≤97（实测 hg-scene_74-020 恰落 97.0）；elements_score=0.833 → ≤95.8；带 source 且保真 1.0 样本仍可到 100；短卡地板（43.1/44.4/55.6/39.7）不塌

#### Scenario: 258 哨兵门禁（重定基）
- **WHEN** CI 运行 python scripts/eval_corpus_258.py
- **THEN** n==258 且 mean≥88.0/ge90≥190/lt60≤30/missing_audio≤40；round3 重定基值 mean=91.0/ge90=216/ge80=225/lt60=20/missing_audio=20（mean -1.3 为缩放封顶设计意图）

