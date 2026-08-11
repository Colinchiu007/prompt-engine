# Design：文案分句 → 提示词 → 生图对比验证

## 架构
```
浏览器 compare-tab.js (Vue3 + Element Plus CDN)
   │  POST /v1/compare/*
   ▼
prompt_engine/api/compare.py (FastAPI router, 无状态)
   ├─ /split   → httpx → smart-sentence-splitter (SPLITTER_BASE_URL:8002)
   ├─ /prompt  → openai client → MiniMax chat/completions (MiniMax-M3)
   └─ /images  → minimax_client.generate_minimax_images → MiniMax image_generation (image-01, n=2)
```

## API Key 流转
请求体 `api_key` > 环境变量 `MINIMAX_API_KEY`；仅存请求局部变量；错误消息清洗（<200 字符、去换行）。

## 错误分级
| 类型 | 触发 | 可重试 | HTTP |
|------|------|--------|------|
| auth | 401/403 | 否 | 400 |
| invalid_config | 无 key/参数非法 | 否 | 400/422 |
| content_safety | 内容安全拒绝 | 否 | 422 |
| empty_result | 200 但无图 | 是 | 422 |
| rate_limit | 429 | 是 | 429 |
| timeout | 超时 | 是 | 504 |
| provider_error/network | 5xx/网络 | 是 | 502/503 |

## 前端状态机（每句独立）
promptState / imageState：idle → loading → done | error；批量操作串行；>30 句与批量生图前确认。

## 安全
- base_url 仅 http(s)://host[/path]（SSRF 缓解）；分句 target 服务端固定（防 SSRF）
- key 不落盘：localStorage（前端，本地单机工具）+ 环境变量（服务端）
- 生图数量上限 4（默认 2）

## 测试
tests/test_compare_api.py 17 例（mock 隔离）：split 校验/代理/503/空结果；prompt 无 key/<think> 剥离/空输出 502；images 无 key/双图/空结果 422/auth 400；minimax_client aspect 解析与错误分级。