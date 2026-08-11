# 文案分句 → 提示词 → 生图对比验证前端

## Why
验证图片提示词实际生成图片的效果：输入文案 → 分句 → 每句生成生图提示词 → 同一提示词 2 张图对比。

## What Changes
- 新增前端「对比验证」页签（`prompt_engine/web/compare-tab.js` + `index.html` 挂载）
- 新增 3 个无状态 API 端点（`prompt_engine/api/compare.py`）：
  - `POST /v1/compare/split`（代理 smart-sentence-splitter）
  - `POST /v1/compare/prompt`（MiniMax LLM 生成英文生图提示词）
  - `POST /v1/compare/images`（MiniMax image-01 生成 n 张图）
- 新增 MiniMax 生图共享助手 `prompt_engine/api/minimax_client.py`（/v1/preview 与 compare/images 复用）
- API Key：请求体透传 > 环境变量 MINIMAX_API_KEY；不落盘、不进日志

## Impact
- 新增文件：compare.py / minimax_client.py / compare-tab.js / tests/test_compare_api.py
- 修改文件：rest.py（include_router + preview 复用）/ index.html / .env.example / docs（PRD/INTEGRATION/CHANGELOG/README）
- 无数据库变更、无依赖新增（httpx/openai/fastapi 均已存在）

## Non-goals
- 不做账号体系、不做历史记录落库、不改 smart-sentence-splitter / Multi-Publish
- 不引入前端构建链（沿用 CDN Vue3 + Element Plus 单页）