# byok-llm-object — Design

## 1. 请求契约（models.py）

- 新增 `LLMBind`：`provider`(≤64)、`model`(≤128)、`base_url`(可选,≤256)、`api_key`(1..512，必填)。
- `OptimizeRequest.llm: Optional[LLMBind] = None`；`OptimizeRequest.caller: Optional[str] = None`（≤64）。
- `user_tier` / `user_own_key` 字段保留以兼容既有 schema，标记弃用（不再影响行为）。
- `OptimizeResult.caller` 透传；llm 路径 `key_source="caller"`。

## 2. provider 工厂（llm/base.py + llm/__init__.py）

- `BaseLLMProvider.from_llm_object(llm: dict)`：校验 provider 在注册表中、api_key/model 非空；sensenova 缺省 base_url=https://token.sensenova.cn/v1。
- OpenAI 兼容族（openai_compat/ai_router/sensenova）→ `OpenAICompatProvider({api_key, model, base_url})`；其他注册 provider 以 `{api_key, model, base_url?}` 构造子类。

## 3. optimizer（optimizer.py）

- 模块级 `requires_llm(request) -> bool`（video 域或图片 creative_level>3），rest 边界与内部同源。
- `optimize(request, provider=None, provider_id="")`：rest 层传入经 llm 对象构建的 provider；
  线程本地 `_local.llm_caller` 绑定 per-request provider，finally 清理防跨请求串用；缺省回退 config 单例。
- 缓存键并入 provider 身份（provider|model|base_url）：`SqlitePromptCache.make_key` 在全部组件后追加
  provider 哈希；`CacheManager` L1/L2 读写均透传同一 provider 身份，避免双级缓存键不一致
  （修复 make_key 的 provider 追加死代码与 SQLite L2 漏传 provider 两个实现缺陷）。
- 模板路径 key 不变（无 provider 时无后缀）。

## 4. REST 边界（api/rest.py）

- `/v1/optimize`：`requires_llm` 且 llm 缺失 → 422；llm 非法（未知 provider/缺 api_key/model）→ 422；模板路径不构造 provider。
- `/v1/optimize/batch`：逐条同规则。
- 移除 user_tier KeyRouter 分支与 `optimize_with_key_router` 死调用；api_key 绝不进入日志。

## 5. 兜底移除

- 删除 `key_router.py` / `ops_client.py`（config.yaml 兜底 + OpsCenter 官方 Key 全部移除）。
- `Optimizer.__init__` 的 config provider 构造改为容错（失败置 None，供 rewrite/reverse 返回可操作错误），保证无 key 部署可启动。

## 6. 兼容性

- 未携带 llm 的模板直出请求（图片 creative_level≤3）行为不变。
- reverse/rewrite/auto-style 端点暂保持 config provider（不在桌面 8013 优化链路，后续迭代对齐）。
