# Changelog

本项目更新日志。

## [v0.24.3] — 2026-08-12

### 记录：对比验证页完整生图对比 UI 级验证（Playwright）

- 真实页面流程全部走通：输入 326 字 → 分句 11 句 → 首句「生成提示词」→ **1288 字英文提示词**（MiniMax LLM）→「生图对比」→ **2 张真实图片渲染**（OSS URL，20.2s）；
- 服务端 `MINIMAX_API_KEY` 注入时 `hasKey=true`，前端免填 Key 即可完整使用；
- 截图：`C:/tmp/parity/ui_compare_images.png`（完整对比视图）。

## [v0.24.2] — 2026-08-12

### 记录：对比验证页 UI 交互验证（Playwright 驱动真实页面）

- 加载 `http://127.0.0.1:8013/web/` → 切「🎞️ 对比验证」页签 → 输入 326 字文案（>300 要求）→ 点击「开始分句」→ **11 句分句结果真实渲染**（页面 tag「11 句」+ 逐句展示）；
- 截图：`C:/tmp/parity/ui_compare.png`（本地验证证据）；
- 补充 v0.24.1 的 API 级验证：交互链路（输入/按钮/结果展示）同样可用。

## [v0.24.1] — 2026-08-12

### 记录：对比验证页（/v1/compare/*）真实端到端验证 + 生图格式契约细节

- **真实验证（用户需求：300 字以上文案 → 分句 → 提示词 → 双图对比）**：326 字山村茶事文案 → `/v1/compare/split` 11 句（经 8002 真实分句）；
  抽样 3 句 → `/v1/compare/prompt` 生成英文生图提示词（MiniMax LLM，8.5~14s/句）→ `/v1/compare/images` 每提示词 2 张（MiniMax image-01，19~60s），共 6 张全部成功且互不相同（SHA-256 验证）；
- **格式契约细节**：MiniMax image-01 `response_format=url` 实际返回 **JPEG**（1024×1024）但 URL 以 `.png` 结尾——浏览器 `<img>` 按内容嗅探可正常显示，无需改前端；记录供下载落盘/二次处理方参考（勿按扩展名假定格式）；
- **API Key 流转验证**：请求体 `api_key` > 环境变量 `MINIMAX_API_KEY`；服务端注入 env key 时前端可免填（`/v1/compare/status.has_env_key=true`）；
- 无 Key 时 `400 MiniMax API Key 未配置`、错误 Key 时 `400 MiniMax 鉴权失败`（fail-closed 契约已按测试验证）。

## [v0.24.0] — 2026-08-12

### 调整：批量优化上限 10 -> 20（+ 有界并发）

- **背景**：真实 E2E（animation 流水线）发现 storyboard 最多产出 12 个视频场景，一次性批量优化触发 `BatchOptimizeRequest` 上限 10 → 422 整线失败。
- **调整**：`/v1/optimize/batch` 单批上限 10 → **20**（覆盖 videogen 12 场景单批 + 余量）；服务端执行从全量并行改为**有界并发（asyncio.Semaphore(8)）**，避免放大上限后对 LLM 造成并发风暴，`gather` 保证结果顺序与请求顺序一致；>20 由客户端分块兜底。
- **测试**：test_batch 上限断言 20 / 超限 21 / 新增 12 条单批合法用例；与 video 领域测试合计通过。

### 变更文件

| 文件 | 说明 |
|------|------|
| `prompt_engine/models.py` | `BatchOptimizeRequest.requests.max_length` 10 -> 20 |
| `prompt_engine/api/rest.py` | batch 有界并发（Semaphore 8）+ docstring |
| `04-tests/test_batch.py` | 上限 20 / 超限 21 / 12 条单批合法 |

## [v0.23.0] — 2026-08-11

### 新增：视频提示词优化（domain=video，Phase 1）

- **视频领域模型** — `models.py` 新增 `DomainType`（image/video，缺省 image 零回归）、`VideoPlatformType`（sora/kling/veo/runway/wan/seedance/minimax/hunyuan/cogvideo/ltx/higgsfield/grok/agnes/generic_video）、`VideoPromptResult`（shot/camera/motion_intensity/scene_transition/continuity_token/duration_hint）；`OptimizeRequest.domain` + platform 联合枚举；`OptimizeResult.video` 可选结构化字段。
- **视频通用策略** — `strategies/video/generic.py`（GenericVideoStrategy，六要素 + 镜头语言 + 结构化 JSON 输出，非法 JSON 规则化回退）；策略注册表按 `domain` 分组（`list_strategies(domain)`）。
- **REST** — `/v1/optimize`、`/v1/optimize/batch` 支持 `domain=video`；`/v1/platforms?domain=video` 返回视频平台；视频领域 creative_level<=3 不走图片模板直出。
- **测试** — `04-tests/test_video_optimize.py` 17 例（domain 缺省兼容/平台别名/结构化输出/空超长 error fail-closed/批量数量/模板跳过）。

### 变更文件

| 文件 | 说明 |
|------|------|
| `prompt_engine/models.py` | 视频领域模型（DomainType/VideoPlatformType/VideoPromptResult/domain/union/video 字段） |
| `prompt_engine/strategies/video/` | 新增视频策略子包（GenericVideoStrategy） |
| `prompt_engine/strategies/base.py` | 策略 domain 属性 + `post_process_video` 默认实现 + `list_strategies(domain)` |
| `prompt_engine/strategies/__init__.py` | 注册视频策略 |
| `prompt_engine/optimizer.py` | 视频路径（domain=video：结构化后处理、generic_video 兜底、跳过模板直出、video 字段填充） |
| `prompt_engine/api/rest.py` | `/v1/optimize(/batch)` domain 支持 + `/v1/platforms?domain=` |
| `04-tests/test_video_optimize.py` | 视频契约测试（17 例） |

## [v0.22.1] — 2026-08-11

### Bug 修复：对比验证页签空白（PR #13）

- **整页空白** — `window.__PE = { api, copyText, isEnglish }` 引用了 Workbench 组件内的局部函数 `copyText`（全局作用域 ReferenceError → 内联脚本中断 → createApp 未执行）。修复：`__PE` 只暴露全局可访问的 `api`。
- **页签空白** — in-DOM 模板 `<CompareTab />`（PascalCase 自闭合标签）被浏览器小写化为 `<comparetab>`，Vue 解析链只能还原为 `Comparetab`，匹配不到注册名 `CompareTab` → 组件未解析、渲染为空原生元素（生产版 Vue 静默无警告）。修复：标签改用 kebab-case `<compare-tab>`。
- **回归保护** — 新增 `tests/test_web_template_contract.py`（3 例静态契约断言：kebab-case 标签、`__PE` 只暴露全局对象、compare-tab.js 加载与注册名匹配）；浏览器级冒烟（真实 Chromium：渲染 → 切页签 → 分句 → 提示词 → 2 图）零错误。

### 变更文件

| 文件 | 说明 |
|------|------|
| `prompt_engine/web/index.html` | 更新 — kebab-case 标签 + `__PE` 作用域修复 |
| `tests/test_web_template_contract.py` | 新增 — 前端模板契约测试（3 例） |
## [v0.22.0] — 2026-08-11

### 新增功能：文案分句 → 提示词 → 生图对比验证

- **「对比验证」页签（web/index.html + web/compare-tab.js）** — 输入 ≤6000 字文案 → 分句模型分句并展示 → 每句经 MiniMax 生成英文生图提示词 → 同一提示词生成 2 张图并排对比；支持单句/批量操作、失败重试、放大预览、API Key 输入（localStorage 记忆 + 环境变量回退）
- **后端 API（prompt_engine/api/compare.py）** — 新增 3 个无状态端点：
  - `POST /v1/compare/split` — 代理 smart-sentence-splitter 分句（`SPLITTER_BASE_URL` 可配，默认 8002，防 SSRF）
  - `POST /v1/compare/prompt` — 单句经 MiniMax LLM 生成英文生图提示词（复用 `strip_reasoning_blocks` 剥离 `<think>`，空输出 502 可重试）
  - `POST /v1/compare/images` — 单提示词经 MiniMax image-01 生成 n 张图（默认 2），HTTP 200 空图显式报错（content_safety / empty_result）
- **生图共享助手（prompt_engine/api/minimax_client.py）** — `/v1/preview` 与 `/v1/compare/images` 复用同一 MiniMax 调用实现；错误分级（auth/rate_limit/timeout/network/content_safety/empty_result/invalid_config）
- **API Key 流转** — 请求体 `api_key` > 环境变量 `MINIMAX_API_KEY`；仅存请求局部变量，不落盘、不进日志
- **测试** — `tests/test_compare_api.py` 新增 17 例（全部 mock 隔离）；PRD 新增第十二章（数据校验/流程/交互/显示项/提示文字/错误分级/成本控制）

### 变更文件

| 文件 | 说明 |
|------|------|
| `prompt_engine/api/compare.py` | 新增 — 对比验证路由（3 端点） |
| `prompt_engine/api/minimax_client.py` | 新增 — MiniMax 生图共享助手 |
| `prompt_engine/api/rest.py` | 更新 — include compare router；/v1/preview 复用共享助手 |
| `prompt_engine/web/compare-tab.js` | 新增 — 对比验证前端组件 |
| `prompt_engine/web/index.html` | 更新 — 新增「对比验证」页签 + window.__PE 共享 |
| `tests/test_compare_api.py` | 新增 — 17 例对比验证 API 测试 |
| `.env.example` | 更新 — 补充 SPLITTER_BASE_URL 说明 |
| `docs/PRD.md` | 更新 — 新增第十二章 |
| `docs/INTEGRATION.md` | 更新 — 补充对比验证端点 |
| `README.md` | 更新 — 使用说明 |
| `openspec/changes/2026-08-11-image-prompt-validation-ui/` | 新增 — OpenSpec 契约文档 |
## [v0.21.1] — 2026-06-25

### P3 架构迁移

- **services 模块** — 从 `platform-orchestrator/services/prompt_service.py` 迁移至 `prompt_engine.services`。提供 `optimize_prompt()` / `optimize_prompts_batch()` 高层次场景→提示词优化服务。旧路径已加废弃 shim，通过 `prompt_engine.services` 代理。
- **`prompt_engine/__init__.py`** — 新增 `optimize_prompt`, `optimize_prompts_batch`, `OptimizePromptResult` 惰性导出

### 变更文件

| 文件 | 说明 |
|------|------|
| `prompt_engine/services/__init__.py` | 新增 — services 模块入口 |
| `prompt_engine/services/prompt_service.py` | 新增 — 从 orchestrator 迁移 |
| `prompt_engine/__init__.py` | 更新 — 惰性导出 services |
| `docs/PRD.md` | 更新 — 新增 3.2 services 模块说明 |
| `platform-orchestrator/services/prompt_service.py` | 更新 — 改为废弃 shim |
| `platform-orchestrator/services/__init__.py` | 更新 — 指向 prompt_engine.services |
| `platform-orchestrator/routers/prompt.py` | 更新 — 导入源切换 |
| `platform-orchestrator/routers/video.py` | 更新 — 导入源切换 |

## [v0.21.0] — 2026-06-16

### P0 Bug 修复

- **A/B 多版本无反应** — `disturb_and_optimize` 中 `perturbations` 原为单字符串而非列表，导致只生成 2 个候选（含原始）。修复：每次循环生成新扰动版本，候选数从 2 增至 4
- **模型下拉只显示1项** — `imageModelsData` 未在 `return` 中导出，Vue 无法访问；另有一处错误的 `setTimeout` fallback 逻辑覆盖数据，已移除

### P1 新增功能

- **MiniMax LLM Provider** — 新增 `prompt_engine/llm/minimax.py`，支持 MiniMax-M3 模型作为提示词优化的 LLM 供应商，在 `llm/__init__.py` 和 `llm/base.py` 中注册，默认 LLM 切换为 `minimax`
- **config.yaml MiniMax 配置** — 新增 `minimax` 区块（`api.minimaxi.com/v1`，模型 `MiniMax-M3`），API Key 通过 `${MINIMAX_API_KEY}` 环境变量注入

### 变更文件

| 文件 | 说明 |
|------|------|
| `prompt_engine/optimizer.py` | `disturb_and_optimize` 修复：`perturbations` 列表化 + `num_augmented` 循环生成 |
| `prompt_engine/web/index.html` | Workbench 组件：`imageModelsData` 加入 `return` 导出，移除错误 `setTimeout` fallback |
| `prompt_engine/llm/minimax.py` | 新增 MiniMax LLM Provider（OpenAI 兼容 API） |
| `prompt_engine/llm/__init__.py` | 注册 `minimax` 供应商 |
| `prompt_engine/llm/base.py` | `from_config` 添加 `minimax` 分支 |
| `config.yaml` | 新增 `minimax` LLM 配置块，默认 provider 改为 `minimax` |

## [v0.20.0] — 2026-06-15

### P0 Bug 修复

- **前端模型下拉修复** — Settings 组件 API 解析逻辑 + 完整 16 模型 fallback（之前只有 2 项）
- **A/B 多版本性能优化** — `disturb_and_optimize` 从串行改为并行 + 30s 超时控制
- **A/B 前端显示修复** — 移除 `v-if="result"` 嵌套依赖，A/B 结果独立显示
- **通用策略提示词优化** — `generic.py` 重写提示词模板，消除重复指令，明确平台无关原则
- **MiniMax API 支持** — 修正 Endpoint (`api.minimaxi.com`) + 真实调用 `image-01` 模型
- **前端 Tab 结构修复** — 删除重复 el-tabs 标签，图片预览 Tab 恢复正常

### 变更文件

| 文件 | 说明 |
|------|------|
| `prompt_engine/web/index.html` | Settings 16 模型 fallback + Tab 结构修复 + 图片预览 Tab |
| `prompt_engine/optimizer.py` | `disturb_and_optimize` 并行化 + 新增 `_call_llm_with_timeout` |
| `prompt_engine/strategies/generic.py` | 提示词模板重写，结构更清晰，输出更通用 |
| `prompt_engine/api/rest.py` | MiniMax Endpoint 修正 + preview 端点添加 MiniMax 真实调用 |

## [v0.19.1] — 2026-06-15

### P2 安全与测试

- **预览端点修复** — Pollinations 死代码移除，默认模型改为 picsum
- **裸 `except:` 修复** — 3 处改为 `except Exception:`，不再吃 SystemExit
- **异常详情掩盖** — 5 个端点 `detail=str(e)` → 通用错误信息 + 服务端 `logger.error`
- **API 端点测试** — 新增 `test_api_endpoints.py`（29 个测试，覆盖 optimize/classify/feedback/cache/preview/batch）

### P3 代码质量

- **StyleCategory 映射归并** — 三份重复 25 维映射归并到 `models.py` 单一定义点
- **classifier.py 异常日志** — 5 处静默 `except` 改为 `logger.debug`
- **死代码清理** — optimizer.py (result=None, _STYLE_CATEGORY_TO_TYPE), cache.py (_DEFAULT_DB_DIR), rest.py (if False yaml)
- **seed_demo_data() 惰性化** — 从模块导入时执行改为首次 stats 请求
- **MCP Server 测试** — 新增 `test_mcp_server.py`
- **.gitignore 完善** — 补充 `__pycache__/`、`*.egg-info/`、`feedback_db.json`、`keyword_weights.json`

### 变更文件

| 文件 | 说明 |
|------|------|
| `prompt_engine/models.py` | 新增 4 个共享映射常量（+300 行） |
| `prompt_engine/optimizer.py` | 删除死代码 32 行，映射改 import |
| `prompt_engine/classifier.py` | 3 份映射改 import，5 处异常加日志（-696 行） |
| `prompt_engine/api/rest.py` | 映射改 import + 异常掩盖 + 惰性 seed（±0 行） |
| `prompt_engine/cache.py` | 删除未用变量 _DEFAULT_DB_DIR |
| `prompt_engine/__init__.py` | 版本号 0.19.0→0.19.1 |
| `.gitignore` | 补充 Python 标准忽略项 |
| `tests/test_api_endpoints.py` | 新增 29 个 API 端点测试 |
| `tests/test_mcp_server.py` | 新增 MCP Server 基础测试 |

### 测试

- 全量测试通过，新增 32 个测试用例（29 API + 3 MCP）
- 版本一致：pyproject.toml / __init__.py / CHANGELOG 全部 v0.19.1

## [v0.19.0] — 2026-06-14

### 新增

- **SQLite 缓存持久化 (F1)** — `prompt_engine/cache.py` 双级缓存（L1 Memory + L2 SQLite），重启不丢失，默认 TTL 48 小时
- **低创意模板直出 (F2)** — creative_level ≤ 3 时用模板引擎直出 prompt，零 LLM 调用，耗时 < 10ms
- **TF-IDF 缓存相似匹配 (F3)** — 基于 sklearn TfidfVectorizer 的 char ngram 余弦相似度，降级到旧 set inclusion 算法
- **缓存统计 API** — `GET /v1/cache/stats` 返回 SQLite + Memory 缓存状态

### 新增文件

| 文件 | 说明 |
|------|------|
| `prompt_engine/cache.py` | SqlitePromptCache + MemoryPromptCache 双级缓存 |
| `prompt_engine/data/` | 缓存数据库目录（自动创建） |
| `tests/test_cache_persistence.py` | 缓存持久化测试（10 个） |
| `tests/test_template_render.py` | 模板直出测试（8 个） |
| `tests/test_similarity_tfidf.py` | TF-IDF 相似度测试（8 个） |

### 变更

- `prompt_engine/optimizer.py` — 集成双级缓存 + 模板直出 + TF-IDF 相似度
- `prompt_engine/api/rest.py` — 新增 `GET /v1/cache/stats` 端点
- `prompt_engine/__init__.py` — 惰性导出 `SqlitePromptCache` / `MemoryPromptCache`，版本号 0.5.0→0.19.0
- `pyproject.toml` — 版本号同步到 0.19.0

### 测试

- 新增 26 个测试用例，全量从 224 → **250**
- 所有测试 mock 隔离，无需 API Key

## [v0.4.0] — 2026-06-12

### 新增

- **`rewrite()`** — 借鉴 Infinity `prompt_rewriter.py`，将简短描述扩展为详细 prompt（含 CFG 参数自动判断）
- **`disturb_and_optimize()`** — 借鉴 Infinity BSC，prompt 扰动增强后多次优化取最佳
- **`BitwiseClassifier`** — 借鉴 Infinity IVC，N 分类拆为 d 个二分类，参数量从 O(N×H) 降到 O(d×H)
- **REST API** — 新增 `POST /v1/rewrite` 和 `POST /v1/disturb-optimize` 端点
- **测试** — 新增 16 个测试用例，全量 70 个

### 变更

- `models.py` — 新增 `RewriteRequest` 数据模型
- `__init__.py` — 导出 `RewriteRequest`
- 策略文件数：7 → 7（无变化，策略重写已在 v0.3.1 完成）

## [v0.3.1] — 2026-06-12

### 变更

**全面重写 7 个策略文件** — 从 [Nano Banana Pro Prompt 库](https://github.com/YouMind-OpenLab/awesome-nano-banana-pro-prompts)（14,292 条社区高质量 prompt）提取各平台最佳写作模式。

### 数据来源

| 源 | 说明 |
|---|---|
| `README.md` (英文) | 14,292 条 prompt，42 个 Use Case 分类 + 17 种 Style 分类 + 15 种 Subject 分类 |
| `README_zh.md` (中文) | 社区中文 prompt 样本，覆盖通义/文心/即梦等国内平台 |
| 分析维度 | 高频术语（光照/镜头/颜色/纹理/构图）、结构模式（主体→动作→环境→光照→风格）、质量修饰词、负面提示词 |

### 各策略文件变更

#### `midjourney.py`（32 → 247 行）

| 新增规则 | 来源 |
|---------|------|
| 风格→画幅映射表 | 摄影=4:3、人像=3:4、风景/动漫=16:9（社区高频组合） |
| `--v 6.1` 默认版本 | 社区当前推荐版本 |
| 风格→`--style raw/expressive` 映射 | 写实/摄影用 raw（少美化），动漫/奇幻用 expressive（多创意） |
| 风格→`--s` 值 | creative_level × 50（50-500 范围） |
| 镜头参数库（8 种） | 85mm f/1.8、50mm f/2.8、35mm f/2.0、Macro、135mm... |
| 光照描述库（10 种） | soft diffused / dramatic side / golden hour / cinematic chiaroscuro / volumetric... |
| 构图描述库（8 种） | rule of thirds / centered / leading lines / golden ratio / bird's eye... |
| 质量修饰词 10 级梯度 | creative_level 1→10 对应从 "simple style" 到 "trending on artstation, HDR, 8k" |

**关键发现**：NBP 库中 85mm 相关 prompt 占比 ~12%，f/1.8 约 8%，golden hour 约 6%。

#### `stable_diffusion.py`（35 → 148 行）

| 新增规则 | 来源 |
|---------|------|
| 12 种风格的 `(quality:1.2)` 前缀词 | 社区 prompt 开头几乎都有 masterpiece/best quality 标签 |
| 13 种风格的负面提示词 | 摄影风格不想要 3D 渲染、动漫不想要写实... |
| 光照权重标签（10 种） | `(natural lighting:1.2)`, `(cinematic lighting:1.3)` 等 |
| 质量前缀词库 | 每个风格一个专用前缀短语 |

**关键发现**：NBP 库中约 70% 的 SD 相关 prompt 使用 `(word:1.2)` 权重语法，SD 对权重语法极其敏感。

#### `dalle.py`（29 → 143 行）

| 新增规则 | 来源 |
|---------|------|
| 14 种风格的详细自然语言描述 | DALL·E 偏好段落式而非标签式 |
| 创意度 1-10 细节链 | 从"简单描述"到"主体全维度+分层场景+多光源+精确配色+材质对比+构图法则" |
| 结构模板（6 步） | SUBJECT → ACTION → ENVIRONMENT → COLOR → LIGHTING → STYLE |

**关键发现**：NBP 库中 DALL·E 类 prompt 几乎不使用 `--ar` 等特殊语法，完全是自然语言。

#### `tongyi.py`（28 → 122 行）

| 新增规则 | 来源 |
|---------|------|
| 13 种风格的中文风格描述 | "可见笔触"、"颜色晕染"、"霓虹灯光" 等精确中文术语 |
| 创意度 1-10 细节级别 | 从"仅主体+动作"到"主体全维度+多层场景+主光/辅光/轮廓光+精确配色+多种材质+构图法则" |
| 社区写作技巧 | 精确颜色（藏蓝/薄荷绿/暖琥珀色）、表情细节、材质词 |

**关键发现**：NBP 社区 prompt 中中文 prompt 质量与英文相当，关键在于精确度而非语言。

#### `yizhang.py`（28 → 86 行）

| 新增规则 | 来源 |
|---------|------|
| 13 种风格的关键词标签 | 文心一格偏好"简洁+明确+具象" |
| 2 个完整写作示例 | 从社区 prompt 提取并改写 |
| 写作技巧（4 类） | "形容词+名词"、具体场景词、氛围词、程度词 |

**关键发现**：文心一格的最佳 prompt 是"关键词+逗号分隔+短句"，不是长段落。

#### `jimeng.py`（28 → 122 行）

| 新增规则 | 来源 |
|---------|------|
| 13 种风格的视觉风格描述 | 即梦偏好"视觉冲击力" |
| 创意度 1-10 冲击力描述 | 4 个档位：简洁 → 视觉冲击 → 光影戏剧化 → 极具视觉震撼力 |
| 4 类社区技巧词库 | 动词（投下/划过/穿透）、色彩（烈焰红/霓虹紫）、光影（逆光/轮廓光）、构图（低角度/仰视/框架式） |

**关键发现**：即梦（字节系）社区 prompt 强调动词的力量感和色彩的饱和度。

#### `generic.py`（28 → 54 行）

| 新增规则 | 来源 |
|---------|------|
| 通用 prompt 结构模板 | 6 步：Subject → Action → Environment → Color → Lighting → Composition |
| 社区高频质量模式 | 颜色精度、光照精度、镜头引用、表情细节、纹理细节 |

### 影响

- **不破坏现有 API** — `build_system_prompt()` 签名不变
- **优化质量预期提升** — 策略指导更精确，LLM 输出更贴近社区最佳实践
- **新增 PORTRAIT / LANDSCAPE 风格** — `models.py` 新增枚举

### 待办

- [ ] 将 NBP prompt 库作为 RAG 知识库，提供 few-shot 增强（Phase 2）
- [ ] 基于 NBP 社区分类数据构建风格模板库 `templates/styles.yaml`


## [v0.4.0] — 2026-06-12

### 新增

- **`rewrite()`** — 借鉴 Infinity `prompt_rewriter.py`，将简短描述扩展为详细 prompt（含 CFG 参数自动判断）
- **`disturb_and_optimize()`** — 借鉴 Infinity BSC，prompt 扰动增强后多次优化取最佳
- **`BitwiseClassifier`** — 借鉴 Infinity IVC，N 分类拆为 d 个二分类，参数量从 O(N×H) 降到 O(d×H)
- **REST API** — 新增 `POST /v1/rewrite` 和 `POST /v1/disturb-optimize` 端点
- **测试** — 新增 16 个测试用例，全量 70 个

### 变更

- `models.py` — 新增 `RewriteRequest` 数据模型
- `__init__.py` — 导出 `RewriteRequest`
- 策略文件数：7 → 7（无变化，策略重写已在 v0.3.1 完成）


## [v0.5.0] — 2026-06-13

### 新增 (s1-s5 + P0-P4)

#### 核心功能

- **MJ 风格数据库集成 (s2)** — 从 MidJourney-Styles-and-Keywords-Reference 提取 25 维度 2000+ 风格关键词，注入到优化后的 prompt
- **风格分类器 (s3)** — StyleCategoryClassifier 三级流水线：关键词匹配(~0ms) → 向量语义搜索(~50ms) → LLM 零样本(~1s)，25 个 MJ 风格维度多标签
- **风格感知关键词注入 (s5)** — 根据检测到的风格维度定向注入关键词
- **跨平台风格注入 (P0)** — 共享 keyword_injector.py，全部 7 个策略支持风格注入
- **RAG 增强分类器 (P1)** — TF-IDF 向量索引，模糊语义匹配作为分类第二级
- **StyleType 反向推荐 (P1)** — 14 种艺术风格到 25 维 MJ 类别的映射
- **CLI 工具 (P2)** — classify/categories/optimize/recommend/feedback 子命令
- **用户反馈循环 (P3)** — FeedbackStore JSON 持久化，提交/统计/查看
- **反馈驱动权重 (P4)** — keyword_weights.json，分类器自动调整关键词权重

#### API 新增

| 端点 | 说明 |
|------|------|
| POST /v1/classify | 风格分类 |
| GET /v1/styles/categories | 列出所有维度 |
| POST /v1/feedback | 提交反馈 |
| GET /v1/feedback/stats | 反馈统计 |
| GET /v1/feedback/recent | 最近反馈 |
| POST /v1/feedback/apply | 应用反馈到权重 |

### 变更

- models.py — StyleCategory 调整为 25 维（移除 rainbow_of_colors）；新增 FeedbackEntry、FeedbackStats
- __init__.py — 惰性导入；新增导出 FeedbackStore、recommend_categories_for_style
- classifier.py — 三级流水线重写；新增 RAG 索引、向量搜索、权重系统
- strategies/*.py — 所有策略 post_process 新增 preferred_categories 参数
- optimizer.py — 自动风格检测→注入全链路打通
- templates/styles.yaml — 新增 categories 字段，对接 StyleCategory 分类体系

### 新增文件

| 文件 | 说明 |
|------|------|
| keyword_injector.py | 跨平台风格关键词注入 |
| cli.py | 命令行工具 |
| feedback.py | 反馈存储引擎 |
| tests/test_feedback.py | 反馈系统测试(6) |
| tests/test_feedback_weights.py | 权重系统测试(4) |

### 测试

- 70 → **127** 个测试用例
- 运行时间 ~93s → **~25s**（惰性导入优化）

### 依赖

- 新增 scikit-learn>=1.3.0（RAG TF-IDF 向量搜索）


## [v0.6.0] — 2026-06-13

### 新增

- **Agent Skill 分发模式 (F1)** — 从 awesome-gpt-image-2 复用的 Claude Agent Skill 设计。`agents/skills/prompt-engine/SKILL.md` + 安装脚本（`npm run install:skill`），支持 Claude Code / Cursor / Hermes 自动识别安装
- **RAG 种子注入 (F2)** — 导入 awesome-gpt-image-2 的 506 个 GPT-Image2 案例到向量库，作为分类器的 RAG 种子数据
- **Prompt-as-Code 模板引擎 (F3)** — `prompt_engine/template_engine.py`，原子化 PromptBlock + 组合 PromptTemplate，低创意等级(1-3)可纯模板渲染不调 LLM

### 新增文件

| 文件 | 说明 |
|------|------|
| `agents/skills/prompt-engine/SKILL.md` | Agent Skill 主文件 |
| `agents/skills/prompt-engine/bin/install.mjs` | 安装脚本 |
| `agents/skills/prompt-engine/package.json` | NPM 发布配置 |
| `agents/skills/prompt-engine/references/api-reference.md` | API 参考 |
| `examples/seed_rag_from_gptimage2.py` | RAG 种子注入脚本 |
| `prompt_engine/template_engine.py` | Prompt-as-Code 模板引擎 |
| `tests/test_rag_seed.py` | RAG 种子测试(4) |
| `tests/test_prompt_template.py` | 模板引擎测试(10) |

### 测试

- 127 → **141** 个测试用例

### 依赖

- 新增：无（模板引擎纯 Python 标准库）
- RAG 种子脚本依赖已有 sklearn


- **F4** — 自定义模板支持 (StyleType → StyleCategory)
- **F5** — RAG 增强分类器 (TF-IDF 向量检索)
- **F6** — 跨平台风格关键词注入 (SD/DALL·E 等)
- **F7** — Agent Skill 风格注入反向推荐

## [v0.7.0] — 2026-06-13

### 新增

- **模板驱动优化 (F1)** — 借鉴 prompt-optimizer，将策略 LLM 指令抽取为独立 YAML 模板文件（`templates/prompts/`），EN/ZH 双语支持，自动回退
- **多模型供应商 (F2)** — 新增 Gemini provider（`llm/gemini.py`），供应商注册表 `list_providers()` / `create_provider()`
- **评估对比 (F3)** — `prompt_engine/evaluator.py`，5 维度 LLM 评估（clarity/specificity/creativity/actionability/platform_best），`POST /v1/evaluate` 端点
- **Web 看板 (F9)** — Vue 3 + Element Plus 全功能界面（Prompt 工作台 / 数据看板 / 配置面板）

### 新增文件

| 文件 | 说明 |
|------|------|
| `prompt_engine/templates/prompts/midjourney/en.yaml` | MJ 模板（EN） |
| `prompt_engine/templates/prompts/generic/en.yaml` | 通用模板（EN） |
| `prompt_engine/llm/gemini.py` | Gemini 供应商 |
| `prompt_engine/llm/__init__.py` | 重写：供应商注册表 |
| `prompt_engine/evaluator.py` | 评估对比引擎 |
| `tests/test_template_loader.py` | 模板加载测试(6) |
| `tests/test_providers.py` | 供应商测试(6) |
| `tests/test_evaluator.py` | 评估测试(8) |
| `examples/seed_rag_from_gpt4o_prompts.py` | gpt4o-image-prompts 1050 案例 RAG 种子 |
│ `tests/test_gpt4o_prompts.py` | gpt4o 数据解析测试(4) |
│ `prompt_engine/dsl_parser.py` | DSL 模板语法解析器 |
│ `prompt_engine/templates/wildcards.yaml` | 通配符池（10 类） |
│ `tests/test_dsl_parser.py` | DSL 语法测试(12) |
│ `prompt_engine/web/index.html` | Web 看板（Vue 3） |
│ `tests/test_dashboard_api.py` | 看板统计测试(4) |

### 变更

- `template_engine.py` — PromptBlock 新增 `use_dsl` 参数，支持 DSL 模板语法
- `dsl_parser.py` — 新增通配符 YAML 加载器 `load_wildcards_from_yaml()`

### 测试

- 141 → **181** 个测试用例

### 依赖

- 新增：`google-genai`（可选，Gemini 供应商需要）


## [v0.8.0] — 2026-06-13














## [v0.15.0] — 2026-06-13

### 新增

- **中文翻译显示 (F1)** — 优化结果若为英文，下方显示「🇨🇳 中文翻译」折叠区

### 翻译实现

- `prompt_engine/translation.py` — Python 单元（200+ 词中英对照表 + 翻译函数）
- Workbench 前端嵌入同款字典 + 函数（纯静态 0 成本）
- 仅当原文 ASCII 比例 > 30% 才显示翻译区
|- 提示「仅供展示，请复制英文原文用于图片生成平台」
|## [v0.16.0] — 2026-06-14
|
|### 新增
|
|- **输入验证 (F1)** — API 层中文 < 3 字/英文 < 3 词返回 400 + 友好提示「描述太简短」
|- **System Prompt 改进 (F1.5)** — MJ/SD/DALL·E 等策略新增短文本处理规则，避免 LLM 自动生成无关画面
|- **前端提示 (F2)** — Workbench 验证失败时显示中文引导文字
|
|### 新增文件
|
|| 文件 | 说明 |
||------|------|
|| `prompt_engine/rest_validation.py` | 输入验证逻辑（33 行） |
|| `tests/test_v016_validation.py` | 验证测试（6 个） |
|
|### 变更
|
|- `prompt_engine/api/rest.py` — 优化端点集成输入验证
|- `prompt_engine/strategies/midjourney.py` — 新增短文本处理规则
|- `docs/PM-PRD-v0.16.0.md` — 产品需求文档
|
|## [v0.16.1] — 2026-06-14
|
|### 新增
|
|- **输入引导面板 (F1)** — 短文本拒绝时不再显示简单 error banner，改为交互式引导面板
|- **主题按钮** — 6 个主题卡片（风景/动物/人物/科幻/抽象/奇幻），点击自动填充示例 prompt
|- **一键示例** — 点击示例文本自动填入输入框
|
|### 变更
|
|- `prompt_engine/web/index.html` — 新增引导面板 UI（58 行）
|- 点击[× 关闭]面板消失，正常错误仍显示 error banner
|- `docs/PM-PRD-v0.16.1.md` — 产品需求文档
|
|### 修复
|
|- **Workbench 渲染修复** — `feedbackMsg`/`inputRows` 未声明导致 Vue 渲染异常
|- **输入验证 fix** — 短文本（好吧/嗯/好的）自动拒绝
|- 新增 `tests/test_qa_comprehensive.py` — QA 综合检查脚本（109 行）
|
|## [v0.17.0] — 2026-06-14
|
|### 变更
|
|- **速度优化** — 默认 max_length 500→300，优化耗时从 7s→4s
|- **速度模式选择器** — Workbench 新增 dropdown 3 档：
|
|| 模式 | max_length | creative_level | 目标耗时 |
||------|-----------|---------------|---------|
|| ⚡ 快速 | 150 | 4 | ~2s |
|| 🎯 标准（默认） | 300 | 6 | ~4s |
|| 📖 详细 | 500 | 8 | ~7s |
|
|### 变更文件
|
|- `prompt_engine/models.py` — OptimizeRequest 默认 max_length 500→300
|- `prompt_engine/web/index.html` — 速度模式下拉框（+9 行）
|- `tests/test_v017_speed.py` — 速度测试（3 个）
|- `docs/PM-PRD-v0.17.0.md` — 产品需求文档
|
|### 测试
|
|- 3 个新增速度测试全部通过
|- 缓存命中仍保持 0ms
|
|## [v0.18.0] — 2026-06-14
|
|### 新增
|
|- **中文输入自动英文输出 (F1)** — 所有 7 个策略（MJ/SD/DALL·E/通义/文心/即梦/通用）的 system prompt 中「输出语言」规则改为"ENGLISH ONLY"，中文用户输入自动输出英文 prompt
|- **检测逻辑 (F3)** — 输出几乎总是英文，`isEnglish()` 检测仍有效，中文翻译面板（v0.15.0）正常显示
|
|### 变更
|
|- 修改 7 个策略文件的 `build_system_prompt`：
|  - `midjourney.py` / `stable_diffusion.py` / `dalle.py` / `tongyi.py`
|  - `yizhang.py` / `jimeng.py` / `generic.py`
|- `prompt_engine/models.py` — 默认语言策略调整
|- `tests/test_v018_english_output.py` — 英文输出测试（3 个）
|- `docs/PM-PRD-v0.18.0.md` — 产品需求文档
|
|### 验收
|
|- 输入「一只威严的猫」→ 输出英文
|- 输入 "a majestic cat" → 输出英文
|- 中文翻译面板仍正常显示
|
|### 测试
|
|- 全量 224/224 测试通过（212 + 6 + 3 + 3）
|
|## [v0.14.0] — 2026-06-13

### 文档

MANUAL.md 包含：
- 快速开始（3 种方式）
- Web 界面使用指南（工作台/看板/配置）
- CLI 使用指南（5 个子命令）
- API 使用指南（17 个端点 + Python 示例）
- 高级功能（RAG/反馈闭环/缓存池/风格注入）
- 部署指南（Docker/手动/环境变量）
- 常见问题（8 个 Q&A）
## [v0.13.0] — 2026-06-13

### 新增

- **README 英文版** — `README.en.md` 完整英文文档，7KB 覆盖所有功能
- **GitHub Actions 徽章** — README.md + README.en.md 顶部显示 CI 状态
- **PyPI 发布配置** — `pyproject.toml` 补充 `[project]` 字段（name/license/classifiers）

### 改进

- 中文 README.md 保持不动，新增英文版独立维护
- README.en.md 覆盖：Quick Start / CLI / REST API / Architecture / Configuration / Contributing

### 测试

- 212/212 测试通过
## [v0.12.0] — 2026-06-13

### 新增

- **反馈闭环 UI (F1)** — 优化结果下方赞/踩按钮，提交到 `/v1/feedback` 端点
- **A/B 多版本 (F2)** — Workbench 新按钮，调用 `/v1/disturb-optimize` 生成 3 个版本择优

### 改进

- 反馈即时 Toast 确认
- 3 个版本并行对比，默认选中最佳版本
- 每个版本可「选用」或「复制」
## [v0.11.0] — 2026-06-13

### 新增

- **关键词注入可视化 (F10)** — `GET /v1/keywords` 端点，Workbench 展示 100 条推荐关键词
- **风格维度选择器 (F11)** — Workbench 新增 13 种风格下拉框（水彩/油画/动漫/赛博朋克/奇幻等）
- **扩写 UI (F12)** — Workbench 新增扩写区域，输入简写 prompt → 一键扩写到 300 词

### 改进

- 优化请求发送 style 参数（选填）
- `GET /v1/styles/categories` 返回 25 维完整清单
- Workbench 布局优化：风格选择 + 扩写 + 主优化互不干扰

### 测试

- 203/203 测试通过（198 → 203, +6 v0.11.0 + 5 E2E）
## [v0.10.0] — 2026-06-13

### 新增

- **Dockerfile + docker-compose** - 一键容器化部署（`docker-compose up`）
- **GitHub Actions CI** - PR 推 master 自动跑 212 个测试
- **批量优化 UI** - Workbench 单条/批量模式切换，max 10 prompts/批

### 改进

- Workbench 增加模式切换（单条 ↔ 批量）
- 批量进度条 + 每条独立结果 + 复制按钮
- v-if 包裹方式统一（div wrapper）

### 测试

- 212 tests (198 + 8 v0.10.0 + 6 E2E)
- TDD: 4 RED → GREEN（Dockerfile + workflow + 批量 UI）
- CI 工作流：unit + E2E + health check
## [v0.9.3] — 2026-06-13

### 改动

- **移除 Pollinations** - 永久下线（自 2026-06-13 起 402）
- **新增 MiniMax image-01** - 国内可直连的高质量图像生成
- **新增 Vidu** - 生数科技文生图

### 端点

- `GET /v1/image-models` 现返回 16 个模型（移除 Pollinations, 新增 MiniMax, Vidu）
- 默认 model 仍为 picsum

### 测试

- 198/198 测试通过
- 删除 2 个 pollinations 相关测试
## [v0.9.2] — 2026-06-13

### 新增

- **Dashboard 测试数据填充** - 启动时自动注入 50 条模拟数据到 stats_store
- **缓存键扩展** - 包含 (creative_level, max_length, negative_prompt, num_candidates) 避免参数变更时的误命中

### 修复

- `optimizer.py` UnboundLocalError (OptimizeResult 局部变量)
- 缓存 hit/miss 不同 platform 区分
- `_PromptCache` 写入时机修正

### 测试

- 全量测试 200/200 通过
- test_seed.py 新增 4 个种子数据测试

## [v0.9.0] — 2026-06-13

### 新增

- **Prompt 内存缓存池（默认启用）** - 相同 prompt 优化 0ms，tokens 0，费用节约 ≥ 90%

### 测试

- 全量测试 200 个用例（190 + 1 cache test）
- 测试通过率 100%

### 新增文件

| 文件 | 说明 |
|------|------|
| `optimizer.py` | 更新 120 行：缓存基础设施 |
| `tests/test_cache.py` | 缓存功能测试（3 个） |
| `docs/ARCH-F4-cache.md` | 架构设计文档（v0.9.0） |
| `docs/PM-PRD-v0.9.0.md` | 产品需求文档（v0.9.0） |

### 技术细节

- `optimizer.py` 新增 `_PromptCache: dict[tuple[str, str], OptimizeResult]`
- `_similarity()` 相似度匹配（string normalization + set inclusion）
- `optimize()` 首层缓存检查，命中返回 duration_ms=0 + tokens_used=0

### 性能指标

- 重复 prompt 命中：0ms, 0 tokens
- 10 次相同优化：从 10 tokens → 1 tokens
- 费用节约：≥ 90%

### 后续

- v0.9.2 将加入 Redis 缓存（多服务器共享）
- v1.0 将加入 LRU 容量限制


- **Prompt 内存缓存池（默认启用）** - 相同 prompt 优化 0ms，tokens 0，费用节约 ≥ 90%

### 技术细节

- `optimizer.py` 新增 `_PromptCache: dict[tuple[str, str], OptimizeResult]`
- `_similarity()` 相似度匹配（string normalization + set inclusion）
- `optimize()` 首层缓存检查，命中返回 duration_ms=0 + tokens_used=0

### 性能指标

- 重复 prompt 命中：0ms, 0 tokens
- 10 次相同优化：从 10 tokens → 1 tokens

### 后续

- v0.9.2 将加入 Redis 缓存（多服务器共享）
- v1.0 将加入 LRU 容量限制


### 迭代历史（F1-F12）
### 迭代历史（F1-F12）

| 阶段 | 内容 |
|------|------|
| **F1-F3** | Agent Skill 分发 / RAG 种子注入 / Prompt-as-Code 模板引擎（v0.6.0） |
| **F4** | 自定义模板支持（v0.5.0） |
| **F5** | RAG 增强分类器（v0.5.0） |
| **F6** | 跨平台风格关键词注入（v0.5.0） |
| **F7** | Agent Skill 风格注入反向推荐（v0.5.0） |
| **F8** | DSL 模板语法（v0.7.0） |
| **F9** | Web 看板（v0.7.0） |
| **F10** | 资源展示（v0.8.0） |
| **F11** | 图片预览（v0.8.0） |
| **F12** | 模型 API 配置（v0.8.0） |

### 新增

- **资源展示 (F1)** — Dashboard 显示引擎完整资源（7 平台 / 936 RAG 案例 / 2100+ MJ 关键词 / 25 风格 / 3 LLM 供应商 / 100+ 通配符 / 2 模板）
- **图片预览 (F2)** — Workbench 优化结果下方集成 14 个图片模型预览，Pollinations 完全免费无需 Key
- **模型配置 (F3)** — Settings 新增图片生成模型清单 + API Key 环境变量配置

### 新增文件

| 文件 | 说明 |
|------|------|
| `tests/test_resources_preview.py` | 资源+预览+模型清单测试(9) |
| `prompt_engine/api/rest.py` | 新增 3 个端点：`/v1/resources`, `/v1/image-models`, `/v1/preview` |

### 测试

- 181 → **190** 个测试用例
## [未发布] 功能：独立视频提示词优化引擎 video_prompt_engine（与图片引擎完全分离，2026-08-12）

- **独立包**：`video_prompt_engine/`（models/strategies/knowledge/optimizer/llm/api），不 import `prompt_engine.*`，运行时与图片引擎（8013）完全解耦；独立服务端口 8020。
- **技术机制复刻**：Optimizer 编排（缓存→策略→system prompt→context→RAG few-shot→LLM→结构化后处理）、策略 @register 注册表、TF-IDF 知识库、LLM 供应商、批量契约（≤20、并发 8、顺序一致、fail closed）。
- **视频知识库（7 开源仓库复用）**：img-prompt（5040 标签→7 维度 2059 关键词）、awesome-video-prompts（11 结构化视频提示词种子）、seedance2-skill（Seedance @引用/多模态策略指令）、awesome-seedance（商用用例）、drama-skills（分镜模板）、stable-diffusion-videos（参考）。
- **共用性原则**：few-shot 只用视频种子；图片知识的视觉维度（光影/色彩/风格/场景）以关键词形式提炼注入（不共享图片种子库）。
- **策略**：generic_video（六要素+Fact-Fidelity）、seedance（@引用/多模态）；结构化输出 shot/camera/motion_intensity/scene_transition/continuity_token/duration_hint。
- **测试**：video_prompt_engine 21/21（含无 import prompt_engine 独立断言）；图片引擎回归 25/25 零回归。

# Changelog

本项目更新日志。

## [v0.24.2] — 2026-08-12

### 记录：对比验证页 UI 交互验证（Playwright 驱动真实页面）

- 加载 `http://127.0.0.1:8013/web/` → 切「🎞️ 对比验证」页签 → 输入 326 字文案（>300 要求）→ 点击「开始分句」→ **11 句分句结果真实渲染**（页面 tag「11 句」+ 逐句展示）；
- 截图：`C:/tmp/parity/ui_compare.png`（本地验证证据）；
- 补充 v0.24.1 的 API 级验证：交互链路（输入/按钮/结果展示）同样可用。

## [v0.24.1] — 2026-08-12

### 记录：对比验证页（/v1/compare/*）真实端到端验证 + 生图格式契约细节

- **真实验证（用户需求：300 字以上文案 → 分句 → 提示词 → 双图对比）**：326 字山村茶事文案 → `/v1/compare/split` 11 句（经 8002 真实分句）；
  抽样 3 句 → `/v1/compare/prompt` 生成英文生图提示词（MiniMax LLM，8.5~14s/句）→ `/v1/compare/images` 每提示词 2 张（MiniMax image-01，19~60s），共 6 张全部成功且互不相同（SHA-256 验证）；
- **格式契约细节**：MiniMax image-01 `response_format=url` 实际返回 **JPEG**（1024×1024）但 URL 以 `.png` 结尾——浏览器 `<img>` 按内容嗅探可正常显示，无需改前端；记录供下载落盘/二次处理方参考（勿按扩展名假定格式）；
- **API Key 流转验证**：请求体 `api_key` > 环境变量 `MINIMAX_API_KEY`；服务端注入 env key 时前端可免填（`/v1/compare/status.has_env_key=true`）；
- 无 Key 时 `400 MiniMax API Key 未配置`、错误 Key 时 `400 MiniMax 鉴权失败`（fail-closed 契约已按测试验证）。

## [v0.24.0] — 2026-08-12

### 调整：批量优化上限 10 -> 20（+ 有界并发）

- **背景**：真实 E2E（animation 流水线）发现 storyboard 最多产出 12 个视频场景，一次性批量优化触发 `BatchOptimizeRequest` 上限 10 → 422 整线失败。
- **调整**：`/v1/optimize/batch` 单批上限 10 → **20**（覆盖 videogen 12 场景单批 + 余量）；服务端执行从全量并行改为**有界并发（asyncio.Semaphore(8)）**，避免放大上限后对 LLM 造成并发风暴，`gather` 保证结果顺序与请求顺序一致；>20 由客户端分块兜底。
- **测试**：test_batch 上限断言 20 / 超限 21 / 新增 12 条单批合法用例；与 video 领域测试合计通过。

### 变更文件

| 文件 | 说明 |
|------|------|
| `prompt_engine/models.py` | `BatchOptimizeRequest.requests.max_length` 10 -> 20 |
| `prompt_engine/api/rest.py` | batch 有界并发（Semaphore 8）+ docstring |
| `04-tests/test_batch.py` | 上限 20 / 超限 21 / 12 条单批合法 |

## [v0.23.0] — 2026-08-11

### 新增：视频提示词优化（domain=video，Phase 1）

- **视频领域模型** — `models.py` 新增 `DomainType`（image/video，缺省 image 零回归）、`VideoPlatformType`（sora/kling/veo/runway/wan/seedance/minimax/hunyuan/cogvideo/ltx/higgsfield/grok/agnes/generic_video）、`VideoPromptResult`（shot/camera/motion_intensity/scene_transition/continuity_token/duration_hint）；`OptimizeRequest.domain` + platform 联合枚举；`OptimizeResult.video` 可选结构化字段。
- **视频通用策略** — `strategies/video/generic.py`（GenericVideoStrategy，六要素 + 镜头语言 + 结构化 JSON 输出，非法 JSON 规则化回退）；策略注册表按 `domain` 分组（`list_strategies(domain)`）。
- **REST** — `/v1/optimize`、`/v1/optimize/batch` 支持 `domain=video`；`/v1/platforms?domain=video` 返回视频平台；视频领域 creative_level<=3 不走图片模板直出。
- **测试** — `04-tests/test_video_optimize.py` 17 例（domain 缺省兼容/平台别名/结构化输出/空超长 error fail-closed/批量数量/模板跳过）。

### 变更文件

| 文件 | 说明 |
|------|------|
| `prompt_engine/models.py` | 视频领域模型（DomainType/VideoPlatformType/VideoPromptResult/domain/union/video 字段） |
| `prompt_engine/strategies/video/` | 新增视频策略子包（GenericVideoStrategy） |
| `prompt_engine/strategies/base.py` | 策略 domain 属性 + `post_process_video` 默认实现 + `list_strategies(domain)` |
| `prompt_engine/strategies/__init__.py` | 注册视频策略 |
| `prompt_engine/optimizer.py` | 视频路径（domain=video：结构化后处理、generic_video 兜底、跳过模板直出、video 字段填充） |
| `prompt_engine/api/rest.py` | `/v1/optimize(/batch)` domain 支持 + `/v1/platforms?domain=` |
| `04-tests/test_video_optimize.py` | 视频契约测试（17 例） |

## [v0.22.1] — 2026-08-11

### Bug 修复：对比验证页签空白（PR #13）

- **整页空白** — `window.__PE = { api, copyText, isEnglish }` 引用了 Workbench 组件内的局部函数 `copyText`（全局作用域 ReferenceError → 内联脚本中断 → createApp 未执行）。修复：`__PE` 只暴露全局可访问的 `api`。
- **页签空白** — in-DOM 模板 `<CompareTab />`（PascalCase 自闭合标签）被浏览器小写化为 `<comparetab>`，Vue 解析链只能还原为 `Comparetab`，匹配不到注册名 `CompareTab` → 组件未解析、渲染为空原生元素（生产版 Vue 静默无警告）。修复：标签改用 kebab-case `<compare-tab>`。
- **回归保护** — 新增 `tests/test_web_template_contract.py`（3 例静态契约断言：kebab-case 标签、`__PE` 只暴露全局对象、compare-tab.js 加载与注册名匹配）；浏览器级冒烟（真实 Chromium：渲染 → 切页签 → 分句 → 提示词 → 2 图）零错误。

### 变更文件

| 文件 | 说明 |
|------|------|
| `prompt_engine/web/index.html` | 更新 — kebab-case 标签 + `__PE` 作用域修复 |
| `tests/test_web_template_contract.py` | 新增 — 前端模板契约测试（3 例） |
## [v0.22.0] — 2026-08-11

### 新增功能：文案分句 → 提示词 → 生图对比验证

- **「对比验证」页签（web/index.html + web/compare-tab.js）** — 输入 ≤6000 字文案 → 分句模型分句并展示 → 每句经 MiniMax 生成英文生图提示词 → 同一提示词生成 2 张图并排对比；支持单句/批量操作、失败重试、放大预览、API Key 输入（localStorage 记忆 + 环境变量回退）
- **后端 API（prompt_engine/api/compare.py）** — 新增 3 个无状态端点：
  - `POST /v1/compare/split` — 代理 smart-sentence-splitter 分句（`SPLITTER_BASE_URL` 可配，默认 8002，防 SSRF）
  - `POST /v1/compare/prompt` — 单句经 MiniMax LLM 生成英文生图提示词（复用 `strip_reasoning_blocks` 剥离 `<think>`，空输出 502 可重试）
  - `POST /v1/compare/images` — 单提示词经 MiniMax image-01 生成 n 张图（默认 2），HTTP 200 空图显式报错（content_safety / empty_result）
- **生图共享助手（prompt_engine/api/minimax_client.py）** — `/v1/preview` 与 `/v1/compare/images` 复用同一 MiniMax 调用实现；错误分级（auth/rate_limit/timeout/network/content_safety/empty_result/invalid_config）
- **API Key 流转** — 请求体 `api_key` > 环境变量 `MINIMAX_API_KEY`；仅存请求局部变量，不落盘、不进日志
- **测试** — `tests/test_compare_api.py` 新增 17 例（全部 mock 隔离）；PRD 新增第十二章（数据校验/流程/交互/显示项/提示文字/错误分级/成本控制）

### 变更文件

| 文件 | 说明 |
|------|------|
| `prompt_engine/api/compare.py` | 新增 — 对比验证路由（3 端点） |
| `prompt_engine/api/minimax_client.py` | 新增 — MiniMax 生图共享助手 |
| `prompt_engine/api/rest.py` | 更新 — include compare router；/v1/preview 复用共享助手 |
| `prompt_engine/web/compare-tab.js` | 新增 — 对比验证前端组件 |
| `prompt_engine/web/index.html` | 更新 — 新增「对比验证」页签 + window.__PE 共享 |
| `tests/test_compare_api.py` | 新增 — 17 例对比验证 API 测试 |
| `.env.example` | 更新 — 补充 SPLITTER_BASE_URL 说明 |
| `docs/PRD.md` | 更新 — 新增第十二章 |
| `docs/INTEGRATION.md` | 更新 — 补充对比验证端点 |
| `README.md` | 更新 — 使用说明 |
| `openspec/changes/2026-08-11-image-prompt-validation-ui/` | 新增 — OpenSpec 契约文档 |
## [v0.21.1] — 2026-06-25

### P3 架构迁移

- **services 模块** — 从 `platform-orchestrator/services/prompt_service.py` 迁移至 `prompt_engine.services`。提供 `optimize_prompt()` / `optimize_prompts_batch()` 高层次场景→提示词优化服务。旧路径已加废弃 shim，通过 `prompt_engine.services` 代理。
- **`prompt_engine/__init__.py`** — 新增 `optimize_prompt`, `optimize_prompts_batch`, `OptimizePromptResult` 惰性导出

### 变更文件

| 文件 | 说明 |
|------|------|
| `prompt_engine/services/__init__.py` | 新增 — services 模块入口 |
| `prompt_engine/services/prompt_service.py` | 新增 — 从 orchestrator 迁移 |
| `prompt_engine/__init__.py` | 更新 — 惰性导出 services |
| `docs/PRD.md` | 更新 — 新增 3.2 services 模块说明 |
| `platform-orchestrator/services/prompt_service.py` | 更新 — 改为废弃 shim |
| `platform-orchestrator/services/__init__.py` | 更新 — 指向 prompt_engine.services |
| `platform-orchestrator/routers/prompt.py` | 更新 — 导入源切换 |
| `platform-orchestrator/routers/video.py` | 更新 — 导入源切换 |

## [v0.21.0] — 2026-06-16

### P0 Bug 修复

- **A/B 多版本无反应** — `disturb_and_optimize` 中 `perturbations` 原为单字符串而非列表，导致只生成 2 个候选（含原始）。修复：每次循环生成新扰动版本，候选数从 2 增至 4
- **模型下拉只显示1项** — `imageModelsData` 未在 `return` 中导出，Vue 无法访问；另有一处错误的 `setTimeout` fallback 逻辑覆盖数据，已移除

### P1 新增功能

- **MiniMax LLM Provider** — 新增 `prompt_engine/llm/minimax.py`，支持 MiniMax-M3 模型作为提示词优化的 LLM 供应商，在 `llm/__init__.py` 和 `llm/base.py` 中注册，默认 LLM 切换为 `minimax`
- **config.yaml MiniMax 配置** — 新增 `minimax` 区块（`api.minimaxi.com/v1`，模型 `MiniMax-M3`），API Key 通过 `${MINIMAX_API_KEY}` 环境变量注入

### 变更文件

| 文件 | 说明 |
|------|------|
| `prompt_engine/optimizer.py` | `disturb_and_optimize` 修复：`perturbations` 列表化 + `num_augmented` 循环生成 |
| `prompt_engine/web/index.html` | Workbench 组件：`imageModelsData` 加入 `return` 导出，移除错误 `setTimeout` fallback |
| `prompt_engine/llm/minimax.py` | 新增 MiniMax LLM Provider（OpenAI 兼容 API） |
| `prompt_engine/llm/__init__.py` | 注册 `minimax` 供应商 |
| `prompt_engine/llm/base.py` | `from_config` 添加 `minimax` 分支 |
| `config.yaml` | 新增 `minimax` LLM 配置块，默认 provider 改为 `minimax` |

## [v0.20.0] — 2026-06-15

### P0 Bug 修复

- **前端模型下拉修复** — Settings 组件 API 解析逻辑 + 完整 16 模型 fallback（之前只有 2 项）
- **A/B 多版本性能优化** — `disturb_and_optimize` 从串行改为并行 + 30s 超时控制
- **A/B 前端显示修复** — 移除 `v-if="result"` 嵌套依赖，A/B 结果独立显示
- **通用策略提示词优化** — `generic.py` 重写提示词模板，消除重复指令，明确平台无关原则
- **MiniMax API 支持** — 修正 Endpoint (`api.minimaxi.com`) + 真实调用 `image-01` 模型
- **前端 Tab 结构修复** — 删除重复 el-tabs 标签，图片预览 Tab 恢复正常

### 变更文件

| 文件 | 说明 |
|------|------|
| `prompt_engine/web/index.html` | Settings 16 模型 fallback + Tab 结构修复 + 图片预览 Tab |
| `prompt_engine/optimizer.py` | `disturb_and_optimize` 并行化 + 新增 `_call_llm_with_timeout` |
| `prompt_engine/strategies/generic.py` | 提示词模板重写，结构更清晰，输出更通用 |
| `prompt_engine/api/rest.py` | MiniMax Endpoint 修正 + preview 端点添加 MiniMax 真实调用 |

## [v0.19.1] — 2026-06-15

### P2 安全与测试

- **预览端点修复** — Pollinations 死代码移除，默认模型改为 picsum
- **裸 `except:` 修复** — 3 处改为 `except Exception:`，不再吃 SystemExit
- **异常详情掩盖** — 5 个端点 `detail=str(e)` → 通用错误信息 + 服务端 `logger.error`
- **API 端点测试** — 新增 `test_api_endpoints.py`（29 个测试，覆盖 optimize/classify/feedback/cache/preview/batch）

### P3 代码质量

- **StyleCategory 映射归并** — 三份重复 25 维映射归并到 `models.py` 单一定义点
- **classifier.py 异常日志** — 5 处静默 `except` 改为 `logger.debug`
- **死代码清理** — optimizer.py (result=None, _STYLE_CATEGORY_TO_TYPE), cache.py (_DEFAULT_DB_DIR), rest.py (if False yaml)
- **seed_demo_data() 惰性化** — 从模块导入时执行改为首次 stats 请求
- **MCP Server 测试** — 新增 `test_mcp_server.py`
- **.gitignore 完善** — 补充 `__pycache__/`、`*.egg-info/`、`feedback_db.json`、`keyword_weights.json`

### 变更文件

| 文件 | 说明 |
|------|------|
| `prompt_engine/models.py` | 新增 4 个共享映射常量（+300 行） |
| `prompt_engine/optimizer.py` | 删除死代码 32 行，映射改 import |
| `prompt_engine/classifier.py` | 3 份映射改 import，5 处异常加日志（-696 行） |
| `prompt_engine/api/rest.py` | 映射改 import + 异常掩盖 + 惰性 seed（±0 行） |
| `prompt_engine/cache.py` | 删除未用变量 _DEFAULT_DB_DIR |
| `prompt_engine/__init__.py` | 版本号 0.19.0→0.19.1 |
| `.gitignore` | 补充 Python 标准忽略项 |
| `tests/test_api_endpoints.py` | 新增 29 个 API 端点测试 |
| `tests/test_mcp_server.py` | 新增 MCP Server 基础测试 |

### 测试

- 全量测试通过，新增 32 个测试用例（29 API + 3 MCP）
- 版本一致：pyproject.toml / __init__.py / CHANGELOG 全部 v0.19.1

## [v0.19.0] — 2026-06-14

### 新增

- **SQLite 缓存持久化 (F1)** — `prompt_engine/cache.py` 双级缓存（L1 Memory + L2 SQLite），重启不丢失，默认 TTL 48 小时
- **低创意模板直出 (F2)** — creative_level ≤ 3 时用模板引擎直出 prompt，零 LLM 调用，耗时 < 10ms
- **TF-IDF 缓存相似匹配 (F3)** — 基于 sklearn TfidfVectorizer 的 char ngram 余弦相似度，降级到旧 set inclusion 算法
- **缓存统计 API** — `GET /v1/cache/stats` 返回 SQLite + Memory 缓存状态

### 新增文件

| 文件 | 说明 |
|------|------|
| `prompt_engine/cache.py` | SqlitePromptCache + MemoryPromptCache 双级缓存 |
| `prompt_engine/data/` | 缓存数据库目录（自动创建） |
| `tests/test_cache_persistence.py` | 缓存持久化测试（10 个） |
| `tests/test_template_render.py` | 模板直出测试（8 个） |
| `tests/test_similarity_tfidf.py` | TF-IDF 相似度测试（8 个） |

### 变更

- `prompt_engine/optimizer.py` — 集成双级缓存 + 模板直出 + TF-IDF 相似度
- `prompt_engine/api/rest.py` — 新增 `GET /v1/cache/stats` 端点
- `prompt_engine/__init__.py` — 惰性导出 `SqlitePromptCache` / `MemoryPromptCache`，版本号 0.5.0→0.19.0
- `pyproject.toml` — 版本号同步到 0.19.0

### 测试

- 新增 26 个测试用例，全量从 224 → **250**
- 所有测试 mock 隔离，无需 API Key

## [v0.4.0] — 2026-06-12

### 新增

- **`rewrite()`** — 借鉴 Infinity `prompt_rewriter.py`，将简短描述扩展为详细 prompt（含 CFG 参数自动判断）
- **`disturb_and_optimize()`** — 借鉴 Infinity BSC，prompt 扰动增强后多次优化取最佳
- **`BitwiseClassifier`** — 借鉴 Infinity IVC，N 分类拆为 d 个二分类，参数量从 O(N×H) 降到 O(d×H)
- **REST API** — 新增 `POST /v1/rewrite` 和 `POST /v1/disturb-optimize` 端点
- **测试** — 新增 16 个测试用例，全量 70 个

### 变更

- `models.py` — 新增 `RewriteRequest` 数据模型
- `__init__.py` — 导出 `RewriteRequest`
- 策略文件数：7 → 7（无变化，策略重写已在 v0.3.1 完成）

## [v0.3.1] — 2026-06-12

### 变更

**全面重写 7 个策略文件** — 从 [Nano Banana Pro Prompt 库](https://github.com/YouMind-OpenLab/awesome-nano-banana-pro-prompts)（14,292 条社区高质量 prompt）提取各平台最佳写作模式。

### 数据来源

| 源 | 说明 |
|---|---|
| `README.md` (英文) | 14,292 条 prompt，42 个 Use Case 分类 + 17 种 Style 分类 + 15 种 Subject 分类 |
| `README_zh.md` (中文) | 社区中文 prompt 样本，覆盖通义/文心/即梦等国内平台 |
| 分析维度 | 高频术语（光照/镜头/颜色/纹理/构图）、结构模式（主体→动作→环境→光照→风格）、质量修饰词、负面提示词 |

### 各策略文件变更

#### `midjourney.py`（32 → 247 行）

| 新增规则 | 来源 |
|---------|------|
| 风格→画幅映射表 | 摄影=4:3、人像=3:4、风景/动漫=16:9（社区高频组合） |
| `--v 6.1` 默认版本 | 社区当前推荐版本 |
| 风格→`--style raw/expressive` 映射 | 写实/摄影用 raw（少美化），动漫/奇幻用 expressive（多创意） |
| 风格→`--s` 值 | creative_level × 50（50-500 范围） |
| 镜头参数库（8 种） | 85mm f/1.8、50mm f/2.8、35mm f/2.0、Macro、135mm... |
| 光照描述库（10 种） | soft diffused / dramatic side / golden hour / cinematic chiaroscuro / volumetric... |
| 构图描述库（8 种） | rule of thirds / centered / leading lines / golden ratio / bird's eye... |
| 质量修饰词 10 级梯度 | creative_level 1→10 对应从 "simple style" 到 "trending on artstation, HDR, 8k" |

**关键发现**：NBP 库中 85mm 相关 prompt 占比 ~12%，f/1.8 约 8%，golden hour 约 6%。

#### `stable_diffusion.py`（35 → 148 行）

| 新增规则 | 来源 |
|---------|------|
| 12 种风格的 `(quality:1.2)` 前缀词 | 社区 prompt 开头几乎都有 masterpiece/best quality 标签 |
| 13 种风格的负面提示词 | 摄影风格不想要 3D 渲染、动漫不想要写实... |
| 光照权重标签（10 种） | `(natural lighting:1.2)`, `(cinematic lighting:1.3)` 等 |
| 质量前缀词库 | 每个风格一个专用前缀短语 |

**关键发现**：NBP 库中约 70% 的 SD 相关 prompt 使用 `(word:1.2)` 权重语法，SD 对权重语法极其敏感。

#### `dalle.py`（29 → 143 行）

| 新增规则 | 来源 |
|---------|------|
| 14 种风格的详细自然语言描述 | DALL·E 偏好段落式而非标签式 |
| 创意度 1-10 细节链 | 从"简单描述"到"主体全维度+分层场景+多光源+精确配色+材质对比+构图法则" |
| 结构模板（6 步） | SUBJECT → ACTION → ENVIRONMENT → COLOR → LIGHTING → STYLE |

**关键发现**：NBP 库中 DALL·E 类 prompt 几乎不使用 `--ar` 等特殊语法，完全是自然语言。

#### `tongyi.py`（28 → 122 行）

| 新增规则 | 来源 |
|---------|------|
| 13 种风格的中文风格描述 | "可见笔触"、"颜色晕染"、"霓虹灯光" 等精确中文术语 |
| 创意度 1-10 细节级别 | 从"仅主体+动作"到"主体全维度+多层场景+主光/辅光/轮廓光+精确配色+多种材质+构图法则" |
| 社区写作技巧 | 精确颜色（藏蓝/薄荷绿/暖琥珀色）、表情细节、材质词 |

**关键发现**：NBP 社区 prompt 中中文 prompt 质量与英文相当，关键在于精确度而非语言。

#### `yizhang.py`（28 → 86 行）

| 新增规则 | 来源 |
|---------|------|
| 13 种风格的关键词标签 | 文心一格偏好"简洁+明确+具象" |
| 2 个完整写作示例 | 从社区 prompt 提取并改写 |
| 写作技巧（4 类） | "形容词+名词"、具体场景词、氛围词、程度词 |

**关键发现**：文心一格的最佳 prompt 是"关键词+逗号分隔+短句"，不是长段落。

#### `jimeng.py`（28 → 122 行）

| 新增规则 | 来源 |
|---------|------|
| 13 种风格的视觉风格描述 | 即梦偏好"视觉冲击力" |
| 创意度 1-10 冲击力描述 | 4 个档位：简洁 → 视觉冲击 → 光影戏剧化 → 极具视觉震撼力 |
| 4 类社区技巧词库 | 动词（投下/划过/穿透）、色彩（烈焰红/霓虹紫）、光影（逆光/轮廓光）、构图（低角度/仰视/框架式） |

**关键发现**：即梦（字节系）社区 prompt 强调动词的力量感和色彩的饱和度。

#### `generic.py`（28 → 54 行）

| 新增规则 | 来源 |
|---------|------|
| 通用 prompt 结构模板 | 6 步：Subject → Action → Environment → Color → Lighting → Composition |
| 社区高频质量模式 | 颜色精度、光照精度、镜头引用、表情细节、纹理细节 |

### 影响

- **不破坏现有 API** — `build_system_prompt()` 签名不变
- **优化质量预期提升** — 策略指导更精确，LLM 输出更贴近社区最佳实践
- **新增 PORTRAIT / LANDSCAPE 风格** — `models.py` 新增枚举

### 待办

- [ ] 将 NBP prompt 库作为 RAG 知识库，提供 few-shot 增强（Phase 2）
- [ ] 基于 NBP 社区分类数据构建风格模板库 `templates/styles.yaml`


## [v0.4.0] — 2026-06-12

### 新增

- **`rewrite()`** — 借鉴 Infinity `prompt_rewriter.py`，将简短描述扩展为详细 prompt（含 CFG 参数自动判断）
- **`disturb_and_optimize()`** — 借鉴 Infinity BSC，prompt 扰动增强后多次优化取最佳
- **`BitwiseClassifier`** — 借鉴 Infinity IVC，N 分类拆为 d 个二分类，参数量从 O(N×H) 降到 O(d×H)
- **REST API** — 新增 `POST /v1/rewrite` 和 `POST /v1/disturb-optimize` 端点
- **测试** — 新增 16 个测试用例，全量 70 个

### 变更

- `models.py` — 新增 `RewriteRequest` 数据模型
- `__init__.py` — 导出 `RewriteRequest`
- 策略文件数：7 → 7（无变化，策略重写已在 v0.3.1 完成）


## [v0.5.0] — 2026-06-13

### 新增 (s1-s5 + P0-P4)

#### 核心功能

- **MJ 风格数据库集成 (s2)** — 从 MidJourney-Styles-and-Keywords-Reference 提取 25 维度 2000+ 风格关键词，注入到优化后的 prompt
- **风格分类器 (s3)** — StyleCategoryClassifier 三级流水线：关键词匹配(~0ms) → 向量语义搜索(~50ms) → LLM 零样本(~1s)，25 个 MJ 风格维度多标签
- **风格感知关键词注入 (s5)** — 根据检测到的风格维度定向注入关键词
- **跨平台风格注入 (P0)** — 共享 keyword_injector.py，全部 7 个策略支持风格注入
- **RAG 增强分类器 (P1)** — TF-IDF 向量索引，模糊语义匹配作为分类第二级
- **StyleType 反向推荐 (P1)** — 14 种艺术风格到 25 维 MJ 类别的映射
- **CLI 工具 (P2)** — classify/categories/optimize/recommend/feedback 子命令
- **用户反馈循环 (P3)** — FeedbackStore JSON 持久化，提交/统计/查看
- **反馈驱动权重 (P4)** — keyword_weights.json，分类器自动调整关键词权重

#### API 新增

| 端点 | 说明 |
|------|------|
| POST /v1/classify | 风格分类 |
| GET /v1/styles/categories | 列出所有维度 |
| POST /v1/feedback | 提交反馈 |
| GET /v1/feedback/stats | 反馈统计 |
| GET /v1/feedback/recent | 最近反馈 |
| POST /v1/feedback/apply | 应用反馈到权重 |

### 变更

- models.py — StyleCategory 调整为 25 维（移除 rainbow_of_colors）；新增 FeedbackEntry、FeedbackStats
- __init__.py — 惰性导入；新增导出 FeedbackStore、recommend_categories_for_style
- classifier.py — 三级流水线重写；新增 RAG 索引、向量搜索、权重系统
- strategies/*.py — 所有策略 post_process 新增 preferred_categories 参数
- optimizer.py — 自动风格检测→注入全链路打通
- templates/styles.yaml — 新增 categories 字段，对接 StyleCategory 分类体系

### 新增文件

| 文件 | 说明 |
|------|------|
| keyword_injector.py | 跨平台风格关键词注入 |
| cli.py | 命令行工具 |
| feedback.py | 反馈存储引擎 |
| tests/test_feedback.py | 反馈系统测试(6) |
| tests/test_feedback_weights.py | 权重系统测试(4) |

### 测试

- 70 → **127** 个测试用例
- 运行时间 ~93s → **~25s**（惰性导入优化）

### 依赖

- 新增 scikit-learn>=1.3.0（RAG TF-IDF 向量搜索）


## [v0.6.0] — 2026-06-13

### 新增

- **Agent Skill 分发模式 (F1)** — 从 awesome-gpt-image-2 复用的 Claude Agent Skill 设计。`agents/skills/prompt-engine/SKILL.md` + 安装脚本（`npm run install:skill`），支持 Claude Code / Cursor / Hermes 自动识别安装
- **RAG 种子注入 (F2)** — 导入 awesome-gpt-image-2 的 506 个 GPT-Image2 案例到向量库，作为分类器的 RAG 种子数据
- **Prompt-as-Code 模板引擎 (F3)** — `prompt_engine/template_engine.py`，原子化 PromptBlock + 组合 PromptTemplate，低创意等级(1-3)可纯模板渲染不调 LLM

### 新增文件

| 文件 | 说明 |
|------|------|
| `agents/skills/prompt-engine/SKILL.md` | Agent Skill 主文件 |
| `agents/skills/prompt-engine/bin/install.mjs` | 安装脚本 |
| `agents/skills/prompt-engine/package.json` | NPM 发布配置 |
| `agents/skills/prompt-engine/references/api-reference.md` | API 参考 |
| `examples/seed_rag_from_gptimage2.py` | RAG 种子注入脚本 |
| `prompt_engine/template_engine.py` | Prompt-as-Code 模板引擎 |
| `tests/test_rag_seed.py` | RAG 种子测试(4) |
| `tests/test_prompt_template.py` | 模板引擎测试(10) |

### 测试

- 127 → **141** 个测试用例

### 依赖

- 新增：无（模板引擎纯 Python 标准库）
- RAG 种子脚本依赖已有 sklearn


- **F4** — 自定义模板支持 (StyleType → StyleCategory)
- **F5** — RAG 增强分类器 (TF-IDF 向量检索)
- **F6** — 跨平台风格关键词注入 (SD/DALL·E 等)
- **F7** — Agent Skill 风格注入反向推荐

## [v0.7.0] — 2026-06-13

### 新增

- **模板驱动优化 (F1)** — 借鉴 prompt-optimizer，将策略 LLM 指令抽取为独立 YAML 模板文件（`templates/prompts/`），EN/ZH 双语支持，自动回退
- **多模型供应商 (F2)** — 新增 Gemini provider（`llm/gemini.py`），供应商注册表 `list_providers()` / `create_provider()`
- **评估对比 (F3)** — `prompt_engine/evaluator.py`，5 维度 LLM 评估（clarity/specificity/creativity/actionability/platform_best），`POST /v1/evaluate` 端点
- **Web 看板 (F9)** — Vue 3 + Element Plus 全功能界面（Prompt 工作台 / 数据看板 / 配置面板）

### 新增文件

| 文件 | 说明 |
|------|------|
| `prompt_engine/templates/prompts/midjourney/en.yaml` | MJ 模板（EN） |
| `prompt_engine/templates/prompts/generic/en.yaml` | 通用模板（EN） |
| `prompt_engine/llm/gemini.py` | Gemini 供应商 |
| `prompt_engine/llm/__init__.py` | 重写：供应商注册表 |
| `prompt_engine/evaluator.py` | 评估对比引擎 |
| `tests/test_template_loader.py` | 模板加载测试(6) |
| `tests/test_providers.py` | 供应商测试(6) |
| `tests/test_evaluator.py` | 评估测试(8) |
| `examples/seed_rag_from_gpt4o_prompts.py` | gpt4o-image-prompts 1050 案例 RAG 种子 |
│ `tests/test_gpt4o_prompts.py` | gpt4o 数据解析测试(4) |
│ `prompt_engine/dsl_parser.py` | DSL 模板语法解析器 |
│ `prompt_engine/templates/wildcards.yaml` | 通配符池（10 类） |
│ `tests/test_dsl_parser.py` | DSL 语法测试(12) |
│ `prompt_engine/web/index.html` | Web 看板（Vue 3） |
│ `tests/test_dashboard_api.py` | 看板统计测试(4) |

### 变更

- `template_engine.py` — PromptBlock 新增 `use_dsl` 参数，支持 DSL 模板语法
- `dsl_parser.py` — 新增通配符 YAML 加载器 `load_wildcards_from_yaml()`

### 测试

- 141 → **181** 个测试用例

### 依赖

- 新增：`google-genai`（可选，Gemini 供应商需要）


## [v0.8.0] — 2026-06-13














## [v0.15.0] — 2026-06-13

### 新增

- **中文翻译显示 (F1)** — 优化结果若为英文，下方显示「🇨🇳 中文翻译」折叠区

### 翻译实现

- `prompt_engine/translation.py` — Python 单元（200+ 词中英对照表 + 翻译函数）
- Workbench 前端嵌入同款字典 + 函数（纯静态 0 成本）
- 仅当原文 ASCII 比例 > 30% 才显示翻译区
|- 提示「仅供展示，请复制英文原文用于图片生成平台」
|## [v0.16.0] — 2026-06-14
|
|### 新增
|
|- **输入验证 (F1)** — API 层中文 < 3 字/英文 < 3 词返回 400 + 友好提示「描述太简短」
|- **System Prompt 改进 (F1.5)** — MJ/SD/DALL·E 等策略新增短文本处理规则，避免 LLM 自动生成无关画面
|- **前端提示 (F2)** — Workbench 验证失败时显示中文引导文字
|
|### 新增文件
|
|| 文件 | 说明 |
||------|------|
|| `prompt_engine/rest_validation.py` | 输入验证逻辑（33 行） |
|| `tests/test_v016_validation.py` | 验证测试（6 个） |
|
|### 变更
|
|- `prompt_engine/api/rest.py` — 优化端点集成输入验证
|- `prompt_engine/strategies/midjourney.py` — 新增短文本处理规则
|- `docs/PM-PRD-v0.16.0.md` — 产品需求文档
|
|## [v0.16.1] — 2026-06-14
|
|### 新增
|
|- **输入引导面板 (F1)** — 短文本拒绝时不再显示简单 error banner，改为交互式引导面板
|- **主题按钮** — 6 个主题卡片（风景/动物/人物/科幻/抽象/奇幻），点击自动填充示例 prompt
|- **一键示例** — 点击示例文本自动填入输入框
|
|### 变更
|
|- `prompt_engine/web/index.html` — 新增引导面板 UI（58 行）
|- 点击[× 关闭]面板消失，正常错误仍显示 error banner
|- `docs/PM-PRD-v0.16.1.md` — 产品需求文档
|
|### 修复
|
|- **Workbench 渲染修复** — `feedbackMsg`/`inputRows` 未声明导致 Vue 渲染异常
|- **输入验证 fix** — 短文本（好吧/嗯/好的）自动拒绝
|- 新增 `tests/test_qa_comprehensive.py` — QA 综合检查脚本（109 行）
|
|## [v0.17.0] — 2026-06-14
|
|### 变更
|
|- **速度优化** — 默认 max_length 500→300，优化耗时从 7s→4s
|- **速度模式选择器** — Workbench 新增 dropdown 3 档：
|
|| 模式 | max_length | creative_level | 目标耗时 |
||------|-----------|---------------|---------|
|| ⚡ 快速 | 150 | 4 | ~2s |
|| 🎯 标准（默认） | 300 | 6 | ~4s |
|| 📖 详细 | 500 | 8 | ~7s |
|
|### 变更文件
|
|- `prompt_engine/models.py` — OptimizeRequest 默认 max_length 500→300
|- `prompt_engine/web/index.html` — 速度模式下拉框（+9 行）
|- `tests/test_v017_speed.py` — 速度测试（3 个）
|- `docs/PM-PRD-v0.17.0.md` — 产品需求文档
|
|### 测试
|
|- 3 个新增速度测试全部通过
|- 缓存命中仍保持 0ms
|
|## [v0.18.0] — 2026-06-14
|
|### 新增
|
|- **中文输入自动英文输出 (F1)** — 所有 7 个策略（MJ/SD/DALL·E/通义/文心/即梦/通用）的 system prompt 中「输出语言」规则改为"ENGLISH ONLY"，中文用户输入自动输出英文 prompt
|- **检测逻辑 (F3)** — 输出几乎总是英文，`isEnglish()` 检测仍有效，中文翻译面板（v0.15.0）正常显示
|
|### 变更
|
|- 修改 7 个策略文件的 `build_system_prompt`：
|  - `midjourney.py` / `stable_diffusion.py` / `dalle.py` / `tongyi.py`
|  - `yizhang.py` / `jimeng.py` / `generic.py`
|- `prompt_engine/models.py` — 默认语言策略调整
|- `tests/test_v018_english_output.py` — 英文输出测试（3 个）
|- `docs/PM-PRD-v0.18.0.md` — 产品需求文档
|
|### 验收
|
|- 输入「一只威严的猫」→ 输出英文
|- 输入 "a majestic cat" → 输出英文
|- 中文翻译面板仍正常显示
|
|### 测试
|
|- 全量 224/224 测试通过（212 + 6 + 3 + 3）
|
|## [v0.14.0] — 2026-06-13

### 文档

MANUAL.md 包含：
- 快速开始（3 种方式）
- Web 界面使用指南（工作台/看板/配置）
- CLI 使用指南（5 个子命令）
- API 使用指南（17 个端点 + Python 示例）
- 高级功能（RAG/反馈闭环/缓存池/风格注入）
- 部署指南（Docker/手动/环境变量）
- 常见问题（8 个 Q&A）
## [v0.13.0] — 2026-06-13

### 新增

- **README 英文版** — `README.en.md` 完整英文文档，7KB 覆盖所有功能
- **GitHub Actions 徽章** — README.md + README.en.md 顶部显示 CI 状态
- **PyPI 发布配置** — `pyproject.toml` 补充 `[project]` 字段（name/license/classifiers）

### 改进

- 中文 README.md 保持不动，新增英文版独立维护
- README.en.md 覆盖：Quick Start / CLI / REST API / Architecture / Configuration / Contributing

### 测试

- 212/212 测试通过
## [v0.12.0] — 2026-06-13

### 新增

- **反馈闭环 UI (F1)** — 优化结果下方赞/踩按钮，提交到 `/v1/feedback` 端点
- **A/B 多版本 (F2)** — Workbench 新按钮，调用 `/v1/disturb-optimize` 生成 3 个版本择优

### 改进

- 反馈即时 Toast 确认
- 3 个版本并行对比，默认选中最佳版本
- 每个版本可「选用」或「复制」
## [v0.11.0] — 2026-06-13

### 新增

- **关键词注入可视化 (F10)** — `GET /v1/keywords` 端点，Workbench 展示 100 条推荐关键词
- **风格维度选择器 (F11)** — Workbench 新增 13 种风格下拉框（水彩/油画/动漫/赛博朋克/奇幻等）
- **扩写 UI (F12)** — Workbench 新增扩写区域，输入简写 prompt → 一键扩写到 300 词

### 改进

- 优化请求发送 style 参数（选填）
- `GET /v1/styles/categories` 返回 25 维完整清单
- Workbench 布局优化：风格选择 + 扩写 + 主优化互不干扰

### 测试

- 203/203 测试通过（198 → 203, +6 v0.11.0 + 5 E2E）
## [v0.10.0] — 2026-06-13

### 新增

- **Dockerfile + docker-compose** - 一键容器化部署（`docker-compose up`）
- **GitHub Actions CI** - PR 推 master 自动跑 212 个测试
- **批量优化 UI** - Workbench 单条/批量模式切换，max 10 prompts/批

### 改进

- Workbench 增加模式切换（单条 ↔ 批量）
- 批量进度条 + 每条独立结果 + 复制按钮
- v-if 包裹方式统一（div wrapper）

### 测试

- 212 tests (198 + 8 v0.10.0 + 6 E2E)
- TDD: 4 RED → GREEN（Dockerfile + workflow + 批量 UI）
- CI 工作流：unit + E2E + health check
## [v0.9.3] — 2026-06-13

### 改动

- **移除 Pollinations** - 永久下线（自 2026-06-13 起 402）
- **新增 MiniMax image-01** - 国内可直连的高质量图像生成
- **新增 Vidu** - 生数科技文生图

### 端点

- `GET /v1/image-models` 现返回 16 个模型（移除 Pollinations, 新增 MiniMax, Vidu）
- 默认 model 仍为 picsum

### 测试

- 198/198 测试通过
- 删除 2 个 pollinations 相关测试
## [v0.9.2] — 2026-06-13

### 新增

- **Dashboard 测试数据填充** - 启动时自动注入 50 条模拟数据到 stats_store
- **缓存键扩展** - 包含 (creative_level, max_length, negative_prompt, num_candidates) 避免参数变更时的误命中

### 修复

- `optimizer.py` UnboundLocalError (OptimizeResult 局部变量)
- 缓存 hit/miss 不同 platform 区分
- `_PromptCache` 写入时机修正

### 测试

- 全量测试 200/200 通过
- test_seed.py 新增 4 个种子数据测试

## [v0.9.0] — 2026-06-13

### 新增

- **Prompt 内存缓存池（默认启用）** - 相同 prompt 优化 0ms，tokens 0，费用节约 ≥ 90%

### 测试

- 全量测试 200 个用例（190 + 1 cache test）
- 测试通过率 100%

### 新增文件

| 文件 | 说明 |
|------|------|
| `optimizer.py` | 更新 120 行：缓存基础设施 |
| `tests/test_cache.py` | 缓存功能测试（3 个） |
| `docs/ARCH-F4-cache.md` | 架构设计文档（v0.9.0） |
| `docs/PM-PRD-v0.9.0.md` | 产品需求文档（v0.9.0） |

### 技术细节

- `optimizer.py` 新增 `_PromptCache: dict[tuple[str, str], OptimizeResult]`
- `_similarity()` 相似度匹配（string normalization + set inclusion）
- `optimize()` 首层缓存检查，命中返回 duration_ms=0 + tokens_used=0

### 性能指标

- 重复 prompt 命中：0ms, 0 tokens
- 10 次相同优化：从 10 tokens → 1 tokens
- 费用节约：≥ 90%

### 后续

- v0.9.2 将加入 Redis 缓存（多服务器共享）
- v1.0 将加入 LRU 容量限制


- **Prompt 内存缓存池（默认启用）** - 相同 prompt 优化 0ms，tokens 0，费用节约 ≥ 90%

### 技术细节

- `optimizer.py` 新增 `_PromptCache: dict[tuple[str, str], OptimizeResult]`
- `_similarity()` 相似度匹配（string normalization + set inclusion）
- `optimize()` 首层缓存检查，命中返回 duration_ms=0 + tokens_used=0

### 性能指标

- 重复 prompt 命中：0ms, 0 tokens
- 10 次相同优化：从 10 tokens → 1 tokens

### 后续

- v0.9.2 将加入 Redis 缓存（多服务器共享）
- v1.0 将加入 LRU 容量限制


### 迭代历史（F1-F12）
### 迭代历史（F1-F12）

| 阶段 | 内容 |
|------|------|
| **F1-F3** | Agent Skill 分发 / RAG 种子注入 / Prompt-as-Code 模板引擎（v0.6.0） |
| **F4** | 自定义模板支持（v0.5.0） |
| **F5** | RAG 增强分类器（v0.5.0） |
| **F6** | 跨平台风格关键词注入（v0.5.0） |
| **F7** | Agent Skill 风格注入反向推荐（v0.5.0） |
| **F8** | DSL 模板语法（v0.7.0） |
| **F9** | Web 看板（v0.7.0） |
| **F10** | 资源展示（v0.8.0） |
| **F11** | 图片预览（v0.8.0） |
| **F12** | 模型 API 配置（v0.8.0） |

### 新增

- **资源展示 (F1)** — Dashboard 显示引擎完整资源（7 平台 / 936 RAG 案例 / 2100+ MJ 关键词 / 25 风格 / 3 LLM 供应商 / 100+ 通配符 / 2 模板）
- **图片预览 (F2)** — Workbench 优化结果下方集成 14 个图片模型预览，Pollinations 完全免费无需 Key
- **模型配置 (F3)** — Settings 新增图片生成模型清单 + API Key 环境变量配置

### 新增文件

| 文件 | 说明 |
|------|------|
| `tests/test_resources_preview.py` | 资源+预览+模型清单测试(9) |
| `prompt_engine/api/rest.py` | 新增 3 个端点：`/v1/resources`, `/v1/image-models`, `/v1/preview` |

### 测试

- 181 → **190** 个测试用例
