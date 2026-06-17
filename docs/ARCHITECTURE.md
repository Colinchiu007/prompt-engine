# Prompt Engine 架构文档

> 版本: v0.19.1 | 状态: 🔵 回顾性补全

## 1. 系统总览

Prompt Engine (项目 011) 是一个图片生成提示词优化引擎。接收用户的简短描述，输出适配 Midjourney / Stable Diffusion / DALL·E 等 7 个平台的高质量 prompt。支持 Python SDK、REST API、MCP Server、CLI 和 Vue 3 Web 界面四种使用方式。

## 2. 架构分层

```
┌─────────────────────────────────────────────────────┐
│                  Presentation Layer                  │
│  Vue 3 Web (workbench/dashboard/settings)  │  CLI   │
├─────────────────────────────────────────────────────┤
│                   API Layer                          │
│  FastAPI REST (30+ endpoints)  │  MCP Server         │
├─────────────────────────────────────────────────────┤
│                Orchestration Layer                   │
│  Optimizer (optimize/rewrite/reverse/disturb)        │
│  StyleCategoryClassifier (keyword→vector→LLM)        │
│  Evaluator (5-dim prompt evaluation)                 │
├─────────────────────────────────────────────────────┤
│                Strategy Layer                         │
│  midjourney.py  │  stable_diffusion.py  │  dalle.py   │
│  tongyi.py  │  yizhang.py  │  jimeng.py  │  generic.py│
├─────────────────────────────────────────────────────┤
│              LLM Provider Layer                       │
│  openai_compat.py  │  xfyun.py  │  gemini.py         │
├─────────────────────────────────────────────────────┤
│               Infrastructure Layer                    │
│  Cache (SQLite+L1 Memory)  │  Feedback (JSON)        │
│  RAG (chromadb+TF-IDF)  │  Prompt-as-Code Templates  │
└─────────────────────────────────────────────────────┘
```

## 3. 核心数据流

`optimizer.optimize(request)` 的完整流程：

```
请求 → 1. 缓存检查 (L1 Memory → L2 SQLite)
     → 2. [命中] 返回缓存结果 (tokens=0, duration=0)
     → 3. [creative_level ≤ 3] 模板直出 (零 LLM 调用)
     → 4. 加载平台策略 (strategy_cls.build_system_prompt)
     → 5. [auto_detect] 风格分类 (StyleCategoryClassifier)
     → 6. RAG few-shot 注入 (chromadb 相似检索)
     → 7. LLM 调用 (provider.chat)
     → 8. 后处理 (strategy_cls.post_process)
     → 9. 写入双级缓存 (L1+L2)
     → 10. 返回 OptimizeResult
```

## 4. 模块详解

### `models.py` (208+ 行)
所有 Pydantic 数据模型：
- `OptimizeRequest` / `OptimizeResult` — 核心请求/响应
- `BatchOptimizeRequest` — 批量优化
- `ReverseRequest` / `ReverseResult` — 逆向工程
- `RewriteRequest` — prompt 扩写
- `FeedbackEntry` / `FeedbackStats` — 反馈系统
- `PlatformType` (7 枚举) / `StyleType` (14 枚举) / `StyleCategory` (25 枚举)
- 共享映射表：`STYLE_CATEGORY_DB_MAP` / `CATEGORY_CN_NAMES` / `CATEGORY_DESCRIPTIONS`

### `optimizer.py` (~650 行)
核心编排器。管理缓存、调用策略、调度 LLM。关键方法：
- `optimize()` — 单条优化（含模板直出路径）
- `reverse_engineer()` — 图片→prompt
- `rewrite()` — 简短→详细扩写
- `disturb_and_optimize()` — 扰动增强多版本

### `cache.py` (~180 行)
双级缓存：
- `MemoryPromptCache` — L1 内存热点缓存 (max 1000 条目，FIFO)
- `SqlitePromptCache` — L2 SQLite 持久化缓存 (TTL 48h，自动 vacuum)

### `strategies/` (7 文件)
每个文件对应一个平台的 prompt 生成策略。共同接口：
- `build_system_prompt()` — 构建 LLM system prompt
- `post_process()` — 输出格式调整（如 MJ 的 `--ar --v` 参数）

### `classifier.py` (~740 行)
三级流水线分类器：
1. **关键词匹配** (~0ms) — 精确命中关键词
2. **RAG 向量搜索** (~50ms) — TF-IDF 语义匹配
3. **LLM 零样本** (~1s) — 兜底语义理解

### `template_engine.py`
Prompt-as-Code 模板引擎。`PromptBlock` + `PromptTemplate` 可组合渲染，支持 DSL 语法 `{option1|option2}` / `__wildcard__`。

### `llm/`
供应商抽象层，统一 `BaseLLMProvider.chat()` 接口：
- `openai_compat.py` — OpenAI 兼容 API
- `xfyun.py` — 讯飞星火
- `gemini.py` — Google Gemini

### `feedback.py`
反馈闭环。`FeedbackStore` 管理 JSON 持久化，`get_feedback_store()` 单例。

### `api/`
- `rest.py` — FastAPI 应用，30+ 端点（optimize/classify/evaluate/feedback/cache/stats…）
- `mcp_server.py` — MCP 协议服务

### `web/`
单文件 `index.html` (~1070 行)，Vue 3 + Element Plus + ECharts：
- **Workbench** — 优化/分类/评估/预览/批量/扩写
- **Dashboard** — 统计卡片/引擎资源/缓存状态/ECharts 图表
- **Settings** — LLM 供应商/API Key/模型清单

## 5. 数据模型

```
OptimizeRequest {
    prompt: str                     # 用户输入
    platform: PlatformType          # 目标平台
    creative_level: int (1-10)      # 创意度
    style: Optional[StyleType]      # 风格
    max_length: int                 # 输出最大字数
    negative_prompt: Optional[str]  # 负面提示词
    num_candidates: int             # 候选版本数
    auto_detect_style: bool         # 自动风格检测
}

OptimizeResult {
    optimized_prompt: str           # 优化后的 prompt
    platform: PlatformType
    style: Optional[StyleType]
    model_used: str                 # LLM 模型名/模板
    tokens_used: int                # 消耗 tokens
    duration_ms: float              # 耗时
    candidates: list[str]           # 多候选版本
    error: Optional[str]            # 错误信息
}
```

## 6. 测试体系

- 位置：`tests/` 目录，~40 个测试文件
- 框架：pytest，全部 mock 隔离（无需 API Key）
- 类型：单元测试 + FastAPI TestClient 集成测试
- 覆盖层：策略、分类器、缓存、模板引擎、API 端点、反馈、相似度
- 测试数：~250（随版本递增）

## 7. 部署

```bash
# 安装
pip install -e .

# 启动 REST API
python examples/start_rest_server.py

# 启动 MCP Server
python -m prompt_engine.api.mcp_server

# 启动 Streamlit 工作台
streamlit run workbench/app.py

# 运行测试
python -m pytest tests/ -q

# Docker
docker-compose up
```