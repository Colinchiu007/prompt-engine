# Plan: 文案分句 → 提示词 → 生图对比验证前端

## 技术方案（双模型分析结论：Claude + 主代理自析；antigravity 后端不可用已降级）
- **前端 A3**：现有 index.html 加"对比验证"页签 + 独立组件 JS `prompt_engine/web/compare-tab.js`（index.html 只加 ~5 行；复用 CDN Vue/Element Plus 全局与 window.__PE 共享 api）
- **后端**：新增 `prompt_engine/api/compare.py`（APIRouter，3 个无状态端点），rest.py include_router
  - POST /v1/compare/split — 代理 smart-sentence-splitter（SPLITTER_BASE_URL，默认 http://127.0.0.1:8002，不接受前端传 target 防 SSRF）
  - POST /v1/compare/prompt — 单句 → MiniMax chat/completions → 英文生图提示词（复用 strip_reasoning_blocks，空输出 retryable）
  - POST /v1/compare/images — MiniMax image_generation n=2；空 image_urls 显式 error_type=content_safety
- **API Key 流转 C1**：前端输入（浏览器内存/localStorage）随请求透传 + 环境变量 fallback（MINIMAX_API_KEY）；不写服务端日志；验证时从 Multi-Publish profile 解密注入
- **生图成本控制**：>30 句需确认；默认 n=2；"全部生图"按钮显式触发

## 文件范围（⛔ 只允许改这些）
1. `prompt_engine/api/compare.py`（新建）
2. `prompt_engine/api/minimax_client.py`（新建，生图共享助手；rest.py /v1/preview 改为复用）
3. `prompt_engine/api/rest.py`（include_router + preview 复用助手）
4. `prompt_engine/web/compare-tab.js`（新建）
5. `prompt_engine/web/index.html`（菜单+挂载+window.__PE）
6. `.env.example`（SPLITTER_BASE_URL 说明）
7. `tests/test_compare_api.py`（新建）
8. `docs/PRD.md`、`docs/INTEGRATION.md`、`CHANGELOG.md`、`README.md`（文档）
9. `openspec/changes/2026-08-11-image-prompt-validation-ui/{proposal.md,design.md,tasks.md}`（OpenSpec 契约留档）
10. `.ccg/tasks/image-prompt-validation-ui/*`（任务文件）
11. `.ccg/spec/` 回馈（如有沉淀）

## 实现步骤（按序）
- Step 1: minimax_client.py 生图助手（含空图显式报错、超时、错误分级）
- Step 2: compare.py 三端点（split 代理 + prompt 生成 + images）
- Step 3: rest.py 集成（include_router + preview 复用）
- Step 4: compare-tab.js 前端组件（输入区/分句表/提示词/双图对比/设置区）
- Step 5: index.html 集成（菜单、挂载、__PE）
- Step 6: .env.example + 配置
- Step 7: 测试（tests/test_compare_api.py，mock 隔离）
- Step 8: 文档（PRD 详细章节、INTEGRATION 端点、CHANGELOG、README）
- Step 9: 验证（300+ 字文案：启动 splitter 8002 + prompt-engine 8013 + 解密 MiniMax key 注入 → 分句 → 提示词 → 2 图/句）
- Step 10: 双模型审查 → 修复 → 全量测试 → 记忆更新 → push → PR → 合并 → 归档

## 验收标准
- [ ] 6000 字上限校验生效
- [ ] 分句结果完整展示（index/text/tier/confidence/char_count）
- [ ] 每分句生成英文生图提示词（剥离 <think>）
- [ ] 每提示词 2 张图并排对比
- [ ] API Key 输入 + 环境变量 fallback；key 不进日志/提交
- [ ] 空图/超时/鉴权错误有明确提示与重试分级
- [ ] 测试通过（pytest）；无真实 key 硬编码
- [ ] 300+ 字真实文案端到端验证通过
