# ARCH-F6: PROJECT-012 Context 注入

## 目标

1. **Context 字段** — `OptimizeRequest` 承载 PROJECT-012 的上下文数据
2. **角色一致性注入** — optimize() 自动将 context 注入系统提示词
3. **零侵入** — 不修改任何策略文件，不改变现有测试行为

---

## F6: Context 字段设计

### 数据模型

```python
class OptimizeRequest(BaseModel):
    prompt: str
    platform: PlatformType
    # ... 现有字段不变 ...
    context: Optional[dict] = None  # ← 新增
```

### context dict 契约

```yaml
context:
  setting: "阳光沙滩"                    # 当前场景描述
  character:                            # 当前主角
    name: "Tom"
  character_list:                       # 全部角色
    - name: "Tom"
    - name: "Jerry"
  synopsis: "Tom和Jerry在海滩上追逐"     # 故事梗概（自动截断200字）
```

**设计原则**：
- 使用 `dict` 而非强类型模型 → 保持灵活性，PROJECT-012 可扩展子字段
- `None` 默认值 → 向后完全兼容
- 所有子字段可选 → `{}` 空 dict 不报错

---

## F7: Context 注入流程

### 注入位置

```
optimize(request)
│
├─ 0. 缓存检查
├─ 1. 自动风格检测
├─ 2. strategy.build_system_prompt()
│      ↑ 策略层保持纯净，不感知 context
│
├─ 2.5 ● 注入 context → system_prompt  ← 新增
│      │   if request.context:
│      │       system_prompt += "## Character consistency"
│      │       system_prompt += setting / character / character_list / synopsis
│      │       system_prompt += 角色一致性指令（中英双语）
│      │
├─ 3. RAG few-shot 注入
├─ 4. _call_llm(system_prompt, prompt)
└─ 5. post_process()
```

### 注入内容模板

```
## Character consistency / 角色一致性
Setting/场景: {setting}
Current character/当前角色: {character.name}
All characters/全部角色: {name1}, {name2}, ...
Story synopsis/故事梗概: {synopsis[:200]}

- Keep the same character identity (appearance/服装/发型) across all
  images where the same name appears.
- 相同名字的角色在所有图片中保持同一身份（外貌、服装、发型一致）。
```

### 为什么在 optimize() 而非策略层

| 方案 | 优点 | 缺点 |
|------|------|------|
| **① 策略层注入**（每个 strategy 改 build_system_prompt） | 每个策略可定制 | 改 7 个文件，+ 参数透传，破坏纯函数签名 |
| **② optimizer.py 统一注入**（✓ 本方案） | 改 1 个文件，零侵入策略层 | 注入内容固定（足够通用） |
| **③ 策略层开 hook** | 设计优雅 | 过度设计，当前场景不需要 |

### 字段缺失保护

```python
if ctx.get("setting"):           # → 有则加，无则跳过
if ctx.get("character"):         # → 检查 dict 非空
    parts.append(ctx["character"].get("name", ""))
if ctx.get("character_list"):    # → 遍历并过滤无效项
    names = [c["name"] for c in ctx["character_list"] if "name" in c]
if ctx.get("synopsis"):          # → 截断 200 字
    parts.append(ctx["synopsis"][:200])
```

---

## 数据流

```
PROJECT-012                         PROJECT-011
    │                                     │
    │  POST /v1/optimize/batch             │
    │  {                                   │
    │    "requests": [                     │
    │      {                               │
    │        "prompt": "小明走进超市",      │
    │        "platform": "midjourney",     │
    │        "context": {                  │
    │          "setting": "超市",           │
    │          "character": {"name":"小明"},│
    │          "character_list": [         │
    │            {"name":"小明"},           │
    │            {"name":"老板"}            │
    │          ],                          │
    │          "synopsis": "小明去超市..."   │
    │        }                             │
    │      },                              │
    │      { ... }                         │
    │    ]                                 │
    │  }                                   │
    │                                     │
    │────────────────────────────────────>│
    │                                     │
    │                              BatchOptimizeRequest
    │                              → reqs[0].context = {...}
    │                              → reqs[1].context = {...}
    │                              (每条独立注入)
    │                                     │
    │                                     │
    │  [{optimized_prompt, ...}]          │
    │<────────────────────────────────────│
```

### batch 处理细节

`batch_optimize()` 使用 `asyncio.gather` 并发处理多条请求。
每条走独立的 `optimize()` 流程，context 各自携带，互不干扰。

---

## 风险

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| context 字段膨胀 | 低 | 请求体变大 | dict 灵活，PROJECT-012 控制大小 |
| LLM 忽略角色指令 | 中 | 角色仍不一致 | 指令放 system prompt 末尾（LLM 注意力集中处）|
| character_list 过长 | 低 | token 消耗增加 | 提示中只列名字，详细描述由 PROJECT-012 控制 |
| synopsis 超长 | 低 | system prompt 膨胀 | 显式截断 200 字 |
| context 与 prompt 矛盾 | 低 | LLM 困惑 | 由 PROJECT-012 保证一致性，PROJECT-011 不校验 |

---

## 测试策略

| 测试类型 | 方法 | 覆盖 |
|---------|------|------|
| 单元测试 | 直接构造 OptimizeRequest(context=...) | 字段存储/默认值 |
| 逻辑验证 | 模拟 system prompt 注入过程 | 注入内容正确性 |
| 边界测试 | context={}、context 缺字段 | 不崩溃 |
| 向后兼容 | 不传 context | 行为完全不变 |
