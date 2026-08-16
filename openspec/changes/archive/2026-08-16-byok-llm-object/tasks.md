# byok-llm-object — Tasks

1. models.py：LLMBind + OptimizeRequest.llm/caller + OptimizeResult.caller
2. llm/base.py：from_llm_object；llm/__init__.py 注册 sensenova
3. optimizer.py：requires_llm + optimize(provider=, llm_caller=) + 缓存键并入 provider 身份
4. cache_manager.py / cache.py：make_key/get/set 增加 provider 身份参数
5. api/rest.py：422 fail-closed + 移除 KeyRouter 分支
6. 删除 key_router.py / ops_client.py / tests/test_key_router.py
7. 更新受影响测试 + 新增 tests/test_llm_object.py
8. pytest 全绿 + 文档（CHANGELOG/README/openspec 归档）
