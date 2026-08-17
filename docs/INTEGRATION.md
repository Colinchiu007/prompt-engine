# Prompt Engine 集成指南

> 版本: v0.19.1

## 集成方式

| 方式 | 说明 | 入口 |
|------|------|------|
| Python SDK | 作为库导入使用 | `from prompt_engine import Optimizer` |
| REST API | HTTP 接口 | `POST /v1/optimize` 等 30+ 端点 |
| MCP Server | MCP 协议服务 | `python -m prompt_engine.api.mcp_server` |
| CLI 工具 | 命令行 | `prompt-engine optimize --platform midjourney` |
| Agent Skill | Claude/Cursor/Hermes 技能 | `npm run install:skill` |

## REST API 端点

## 优化执行策略与调用方模型（v0.20.1）

`POST /v1/optimize`、`POST /v1/optimize/batch`、`POST /v1/disturb-optimize` 和 MCP `optimize_prompt` 使用同一策略契约：

| 字段 | 语义 |
|---|---|
| `creative_level` | 1-10 的创意/细节强度；引擎不会从文案自动推断它。 |
| 未传 `optimization_strategy` | 默认使用调用方 LLM；缺少绑定返回 422。 |
| `optimization_strategy=template` | 显式选择确定性图片模板；视频请求返回 422。 |
| `optimization_strategy=llm` | 显式使用调用方 `llm`；缺少绑定返回 422。 |
| `optimization_strategy=auto` | 已删除；请求返回 422。 |
| `bypass_cache=true` | 不读也不写优化缓存；适用于用户主动重新生成。 |

LLM 请求必须传入调用方自己的 `llm={provider,model,base_url?,api_key,caller?}`。`caller` 只能嵌套在 `llm` 中；顶层 `caller` 会被拒绝。优化路径不会使用服务端 `config.yaml`、`.env` 或 OpsCenter 的文字 LLM Key 兜底。返回的 `strategy_used`、`key_source`、`model_used`、`caller`、`cache_hit` 用于诊断实际执行路径。

示例：低创意但仍要求使用调用方模型：

```json
{
  "prompt": "一位扶余王子在山城落脚",
  "creative_level": 1,
  "optimization_strategy": "llm",
  "bypass_cache": true,
  "llm": {
    "provider": "sensenova",
    "model": "SenseNova",
    "base_url": "https://token.sensenova.cn/v1",
    "api_key": "<caller-key>",
    "caller": "multi-publish-desktop"
  }
}
```

### 核心优化

| 端点 | 方法 | 说明 |
|------|------|------|
| `/v1/optimize` | POST | 单条 prompt 优化 |
| `/v1/optimize/batch` | POST | 批量优化（最多 10 条） |
| `/v1/reverse` | POST | 图片逆向工程 |
| `/v1/rewrite` | POST | prompt 扩写 |
| `/v1/disturb-optimize` | POST | 扰动增强多版本 |

### 分类

| 端点 | 方法 | 说明 |
|------|------|------|
| `/v1/classify` | POST | 25 维风格分类 |
| `/v1/styles/categories` | GET | 列出所有风格维度 |

### 评估

| 端点 | 方法 | 说明 |
|------|------|------|
| `/v1/evaluate` | POST | 5 维度优化效果评估 |

### 反馈

| 端点 | 方法 | 说明 |
|------|------|------|
| `/v1/feedback` | POST | 提交反馈 |
| `/v1/feedback/stats` | GET | 反馈统计 |
| `/v1/feedback/recent` | GET | 最近反馈 |
| `/v1/feedback/apply` | POST | 应用反馈到权重 |

### 缓存 (v0.19.0)

| 端点 | 方法 | 说明 |
|------|------|------|
| `/v1/cache/stats` | GET | 缓存统计（SQLite + Memory） |

### 数据统计

| 端点 | 方法 | 说明 |
|------|------|------|
| `/v1/stats/overview` | GET | 总请求/成功率/平均耗时 |
| `/v1/stats/categories` | GET | 分类分布 |
| `/v1/stats/platforms` | GET | 平台分布 |
| `/v1/resources` | GET | 引擎资源总览 |

### 资源

| 端点 | 方法 | 说明 |
|------|------|------|
| `/v1/keywords` | GET | 推荐关键词列表 |
| `/v1/image-models` | GET | 图片生成模型清单 |
| `/v1/preview` | POST | 获取图片预览 URL |

### 对比验证（v0.22.0，文案分句 → 提示词 → 生图对比）

| 端点 | 方法 | 说明 |
|------|------|------|
| `/v1/compare/split` | POST | 代理 smart-sentence-splitter 分句（`SPLITTER_BASE_URL`，默认 `http://127.0.0.1:8002`）；请求 `{text≤6000, language, mode}`，响应 `{sentences[], scenes[], tier_used, splitter, duration_ms}` |
| `/v1/compare/prompt` | POST | 单句经 MiniMax LLM（OpenAI 兼容 `chat/completions`）生成英文生图提示词；请求 `{text, api_key?, base_url?, model?}`，自动剥离 `<think>` 推理块，空输出返回 502 可重试 |
| `/v1/compare/images` | POST | 单提示词经 MiniMax image-01 生成 n 张图（默认 2 张）；请求 `{prompt, api_key?, base_url?, n?, width?, height?}`，响应 `{urls[], count, model, duration_ms}`；HTTP 200 但 `image_urls` 为空时显式报错（`content_safety`/`empty_result`） |

> **API Key 流转**：请求体 `api_key` 优先，其次环境变量 `MINIMAX_API_KEY`；Key 仅存于请求局部变量，不落盘、不进日志。
> **SSRF 缓解**：`base_url` 仅允许 `https://host[/path]`（拒绝回环/私网/链路本地/云 metadata 地址，非回环强制 https）；分句服务 target 由服务端 `SPLITTER_BASE_URL` 配置，不接受前端传入。

## CI/CD

### GitHub Actions

- 文件：`.github/workflows/test.yml`
- 触发：PR 推 master
- 步骤：unit tests → E2E tests → health check
- 测试全部 mock 隔离，无需 API Key

### Docker

```bash
docker-compose up
```

Dockerfile 基于 python:3.11-slim，暴露端口 8000。

## 故障恢复

| 场景 | 恢复步骤 |
|------|----------|
| API 500 错误 | 检查服务端日志，`detail` 已掩盖为 "Internal processing error" |
| 缓存损坏 | `rm prompt_engine/data/prompt_cache.db`（重启后自动重建） |
| RAG 索引失败 | 静默降级，不影响 LLM 调用 |
| LLM 调用超时 | 默认超时后返回错误，缓存未被污染 |
| SQLite 不可用 | 自动降级到内存缓存 |
| sklearn 未安装 | TF-IDF 相似度自动降级到旧算法 |
| ChromaDB 未初始化 | RAG 检索跳过，正常调用 LLM |

## 环境变量

| 变量 | 说明 | 必需 |
|------|------|:----:|
| `MINIMAX_API_KEY` | 图片生成/对比页使用的 MiniMax Key，不用于文字优化 | 按需 |
| `SPLITTER_BASE_URL` | 分句服务地址 | 按需 |
| `VOICE_TOOLS_OPENAI_KEY` | TTS 预览用 Open AI Key | 按需 |

## 版本兼容

- Python ≥ 3.11
- 依赖：pydantic / fastapi / uvicorn / httpx / pyyaml / mcp / scikit-learn / numpy
- 可选：chromadb / google-genai

## 与 PROJECT-012 集成

PROJECT-012（Smart Sentence Splitter）通过 HTTP 桥接调用本引擎的 REST API。

### 桥接方式

```
PROJECT-012 (剧本分析 + 分句)
    ↓ prompt + 场景信息
POST /v1/optimize (本引擎)
    ↓ 优化后的 prompt
PROJECT-012 (SRT 字幕 + 分镜输出)
```

关键对接文件：`src/splitter/exporter/prompt_engine_client.py`

### 上下文注入 (v0.19.0+)

PROJECT-012 可通过 `OptimizeRequest.context` 字段注入剧本上下文
（角色名、场景、情绪），引擎自动注入 system prompt 实现角色一致性。
