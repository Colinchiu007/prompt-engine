# byok-llm-object — Proposal

## Why

提示词引擎（8013）当前由服务端 config.yaml 决定 LLM provider/key（KeyRouter：用户 key → OpsCenter 官方 key → config 兜底）。桌面版调用时未携带自身配置的 LLM，实测落到 config.yaml 的 MiniMax key，而不是用户在桌面「模型设置」里配置的 SenseNova 文字推理模型——与「哪个产品调用引擎，就用哪个产品自己配置的 LLM」的 BYOK 目标不符。

## What Changes

- `OptimizeRequest` 新增可选 `llm` 对象（provider/model/base_url/api_key，调用方自带模型绑定）与 `caller`（产品标识）。
- 需要调用 LLM 的优化请求（图片 creative_level>3 或 video 域）**必须携带 llm**，否则 HTTP 422 fail-closed；模板直出路径（图片 creative_level≤3，免 LLM）允许不携带。
- 删除引擎侧 KeyRouter 链路：config.yaml 兜底 key 与 OpsCenter 官方 key 路径不再被 /v1/optimize 使用（key_router.py / ops_client.py 及其测试移除）。
- `OptimizeResult.key_source` 由 llm 对象驱动（caller）。

## Impact

- `prompt_engine/models.py`、`prompt_engine/api/rest.py`、`prompt_engine/optimizer.py`、`prompt_engine/llm/base.py`、`prompt_engine/llm/__init__.py`、`prompt_engine/llm/openai_compat.py`、`prompt_engine/cache_manager.py`、`prompt_engine/cache.py`（缓存键并入 provider 身份）。
- 删除 `prompt_engine/key_router.py`、`prompt_engine/ops_client.py`、`tests/test_key_router.py`。
- 更新受影响测试（test_api_endpoints / test_batch / test_v016_validation / test_v017_speed / test_video_optimize / test_health_during_optimize / test_ai_router_integration）；新增 `tests/test_llm_object.py`。
- 版本 0.19.0 → 0.20.0。
