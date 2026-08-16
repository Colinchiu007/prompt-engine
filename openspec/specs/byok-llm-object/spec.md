# byok-llm-object Specification

## Purpose
提示词引擎（8013）当前由服务端 config.yaml 决定 LLM provider/key（KeyRouter：用户 key → OpsCenter 官方 key → config 兜底），桌面版调用未携带自身配置的 LLM，实测落到 config.yaml 的 MiniMax key，而非用户在桌面「模型设置」里配置的 SenseNova 文字推理模型。本文档定义 BYOK 契约：哪个产品调用引擎，就用哪个产品自己配置的 LLM，并移除引擎侧服务端 key 兜底。

## Requirements
### Requirement: 调用方 LLM 绑定（BYOK）
需要调用 LLM 的优化请求（`domain=video` 或图片 `creative_level>3`）SHALL 由调用方在请求中携带 `llm` 对象（`provider`/`model`/`base_url` 可选/`api_key` 必填）；缺失 `llm` 或 `llm` 非法（未知 provider / 缺 api_key / 缺 model）MUST 返回 HTTP 422 fail-closed，不得回退服务端 key。

#### Scenario: 视频域缺 llm 返回 422
- **WHEN** POST /v1/optimize 携带 domain=video 且无 llm
- **THEN** 返回 422，请求不被处理

#### Scenario: 模板直出免 LLM
- **WHEN** 图片请求 creative_level<=3（未携带 llm）
- **THEN** 走模板直出路径，正常返回优化结果，不要求 llm

### Requirement: caller 标识与结果透传
调用方可携带可选 `caller`（≤64 字符）标识产品；LLM 路径结果 `key_source` MUST 为 `"caller"`，`caller` 字段透传到 `OptimizeResult`。

#### Scenario: 批量逐项注入
- **WHEN** POST /v1/optimize/batch 每一项均携带 llm 与 caller
- **THEN** 每项按同一规则校验与注入，返回结果各自保留 caller 与 key_source=caller

### Requirement: 缓存键并入 provider 身份
缓存键 MUST 并入 provider 身份（`provider|model|base_url`），避免不同 LLM 绑定命中同一缓存项；`SqlitePromptCache.make_key` 与 `CacheManager` L1/L2 读写 MUST 使用同一 provider 身份。

#### Scenario: 不同绑定的缓存隔离
- **WHEN** 同一 prompt 先后以 sensenova 与 deepseek 绑定调用
- **THEN** 两次缓存键不同，互不命中

### Requirement: 移除服务端 key 兜底
引擎 SHALL 删除 config.yaml 兜底 key 与 OpsCenter 官方 Key 路径（key_router.py / ops_client.py 及 optimize_with_key_router 调用）；无 key 部署 MUST 可启动（config provider 构造容错），reverse/rewrite 等未接入 BYOK 的端点返回可操作错误。

#### Scenario: 无 key 部署可启动
- **WHEN** 环境无任何 LLM key 且启动 8013
- **THEN** 服务正常启动，模板直出请求可服务，需 LLM 请求返回 422/可操作错误
