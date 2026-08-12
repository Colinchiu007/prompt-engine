# video-prompt-engine Specification

## Purpose

定义独立视频提示词优化引擎的能力：与图片提示词引擎完全分离的独立服务/知识库/策略/模型；视频专属关键词库（复用 7 个开源仓库）；结构化视频提示词输出与事实保真；批量契约与 fail-closed 校验。

## ADDED Requirements

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
