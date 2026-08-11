# Prompt Engine — PRD v0.9.3

> 项目 011 / 图片生成提示词优化引擎
> 状态：已交付 | 迭代周期：s1-s5 + P0-P4 + F1-F12

---

## 1. 产品概述

### 1.1 一句话定义

将用户原始 prompt 自动优化为适配 Midjourney / Stable Diffusion / DALL·E / 通义万相 / 文心一格 / 即梦 的高质量 prompt，并提供 25 维 MJ 风格分类能力。

### 1.2 目标用户

| 用户 | 场景 | 需求 |
|------|------|------|
| AI 绘画创作者 | 跨平台发图 | 一次输入 → 所有平台最优 prompt |
| 内容团队 | 统一视觉风格 | 品牌风格 → 自动分类+注入关键词 |
| **Prompt 工程师** | 批量分类优化 | CLI/API 批量处理 |
| 开发者 | 集成到自家工具 | Python SDK / REST / MCP |
| **AI Agent** | 安装 Skill 直接调用 | Claude Code / Cursor / Hermes 一键安装 SKILL.md |

### 1.3 核心竞争力（为什么用户选我们）

```
竞品对比：
                        PromptBase    PromptHero    Infinity     Prompt Engine
自建分类引擎                ❌            ❌           ❌          ✅
反馈闭环学习               ❌            ❌           ❌          ✅
跨平台一致                 ❌            ❌           ❌          ✅
三级流水线                 ❌            ❌           ❌          ✅
25 维风格维度              ❌            ❌           ❌          ✅
| CLI 工具                  ❌            ❌           ❌          ✅                      |
| Agent Skill 分发           ❌            ❌           ❌          ✅                      |
| Prompt-as-Code 模板        ❌            ❌           ❌          ✅                      |
| 开源                      ❌            ❌           ✅          ✅                      |
```

### 1.4 依赖的开源项目

| 项目 | 用途 | 协议 |
|------|------|------|
| willwulfken/MidJourney-Styles-and-Keywords-Reference | 25 维风格关键词数据库（2057 词） | MIT |
| YouMind-OpenLab/awesome-nano-banana-pro-prompts | 策略文件数据基础（14292 prompt） | CC0 |
| Infinity | Prompt 扩写 / BSC / IVC 设计模式 | MIT |

---

## 2. 技术架构

### 2.1 系统分层

```
┌──────────────────────────────────────────────────────────────┐
│                        集成层                                 │
│  Python SDK              REST API              CLI            │
│  from prompt_engine      POST /v1/optimize     prompt-engine  │
│  import Optimizer        POST /v1/classify     classify       │
│                          POST /v1/feedback     feedback       │
├──────────────────────────────────────────────────────────────┤
│                        编排层                                  │
│  Optimizer                                                    │
│  ├── optimize()          → 平台策略 → 关键词注入               │
│  ├── reverse_engineer()  → 视觉模型分析                        │
│  ├── rewrite()           → Infinity prompt_rewriter            │
│  └── disturb_and_optimize() → Infinity BSC                    │
├──────────────────┬───────────────────────────────────────────┤
│   分类流水线       │         优化流水线                         │
│                   │                                           │
│  keyword_match     │  7 策略文件                              │
│  (CN_EN synonyms)  │  ├── midjourney (参数映射+--ar/--s)      │
│       ↓            │  ├── stable_diffusion (权重语法)          │
│  vector_rag        │  ├── dalle (自然语言段落)                 │
│  (TF-IDF 500feat)  │  ├── tongyi (中文描写)                   │
│       ↓            │  ├── yizhang (关键词式)                   │
│  llm_classify      │  ├── jimeng (视觉冲击力)                 │
│  (语义理解兜底)     │  └── generic (通用模板)                  │
│                   │                                           │
│  输出: 25 维多标签  │  + keyword_injector.py                   │
│  + 置信度+方法      │  (风格感知注入，所有策略共享)              │
├──────────────────┴───────────────────────────────────────────┤
│                     数据层                                     │
│  mj_style_final.json    (2057 关键词, 25 维)                  │
│  keyword_weights.json   (反馈驱动的权重)                       │
│  feedback_db.json       (用户反馈持久化)                       │
│  prompts_db/chroma.sqlite3 (RAG 知识库)                       │
│  templates/styles.yaml  (14 种风格的模板)
│  agents/skills/prompt-engine (Agent Skill 分发)            │
│  research/gpt4o-image-prompts/src/data/prompts.json (1050 条 RAG 种子) │
│  templates/wildcards.yaml (10 类 100+ 通配符)                         │
│  web/index.html (Vue 3 + Element Plus 看板)                             │
└──────────────────────────────────────────────────────────────┘
```

### 2.2 分类三级流水线（技术要点）

```
输入: "A serene watercolor painting of mountains"

Step 1: keyword_match (~0ms)
  ├── 中文同义词匹配: "水彩" → drawing_and_art_mediums
  ├── 英文关键词匹配: "watercolor" → drawing_and_art_mediums
  ├── CN_SYNONYMS 补充匹配: "mountain" → nature_and_animals
  └── 置信度 ≥ 0.6? → return (fast path)

Step 2: vector_rag (~50ms)  ← 仅在 Step 1 conf < 0.6 时触发
  ├── TF-IDF 向量化 prompt (500 features, char_wb 分析器)
  ├── 余弦相似度匹配 505 个关键词文档
  ├── 按类别聚合得分、归一化
  └── 有结果? → return (semantic path)

Step 3: llm_classify (~1s)  ← 兜底
  ├── 构造分类 prompt（列出所有类别+示例）
  ├── 调用 LLM 做零样本分类
  ├── 解析 JSON 响应
  └── return

输出: StyleCategoryResult
  ├── categories: [nature_and_animals, drawing_and_art_mediums]
  ├── method: "keyword_match"
  └── confidence: 1.0
```

### 2.3 反馈闭环（技术要点）

```
用户提交反馈 (rating + corrected_categories)
       │
       ▼
FeedbackStore.submit()
  └── 追加写入 feedback_db.json
       │
       ▼
CLI: prompt-engine feedback --apply
或 POST /v1/feedback/apply
       │
       ▼
_apply_feedback_to_weights()
  ├── corrected_categories ✓ → 匹配关键词 × 1.15 (boost)
  ├── detected ≠ corrected   → 假阳关键词 × 0.85 (reduce)
  ├── rating ≥ 4 无修正      → 类别微 boost × 1.05
  └── rating ≤ 2 无修正      → 类别微 reduce × 0.9
       │
       ▼
keyword_weights.json 更新
  └── {category: {keyword: weight}}
       │
       ▼
下一次 classify()
  └── _get_weights() 加载 → keyword_match 中 score × weight
```

### 2.4 风格感知关键词注入

```
optimizer.optimize()
  └── auto_detect_style=True
       → StyleCategoryClassifier.classify(prompt)
       → detected_categories: [StyleCategory, ...]
       │
       ▼
  post_process(preferred_categories=[...])
       │
       ▼
  _inject_style_keywords(preferred_categories)
       ├── 从检测到的类别中选关键词
       └── 注入到优化后的 prompt
       
  效果:
  输入: "a cat" + detected=[nature_and_animals, lighting]
  输出: "a fluffy cat, Golden Hour, Volumetric Lighting."
```

---

## 3. 功能规格

### 3.1 API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/v1/optimize` | POST | 正向优化 |
| `/v1/reverse` | POST | 逆向工程 |
| `/v1/classify` | POST | 风格分类 |
| `/v1/styles/categories` | GET | 列出维度 |
| `/v1/batch` | POST | 批量优化 |
| `/v1/rewrite` | POST | Prompt 扩写 |
| `/v1/disturb-optimize` | POST | 扰动增强 |
| `/v1/platforms` | GET | 平台列表 |
| `/v1/feedback` | POST | 反馈提交 |
| `/v1/feedback/stats` | GET | 反馈统计 |
| `/v1/feedback/recent` | GET | 最近反馈 |
| `/v1/feedback/apply` | POST | 应用权重 |

### 3.2 services 模块（v0.21.0+）

`prompt_engine.services` 提供高层次场景→提示词优化服务，从 `platform-orchestrator` 迁移而来：

| 函数 | 说明 |
|------|------|
| `optimize_prompt(text, segments, ...)` | 场景文本 → 图像提示词。先试 Optimizer，失败退化为直接 LLM 调用 |
| `optimize_prompts_batch(scenes, ...)` | 批量场景优化 |

依赖：`httpx`（LLM 回退调用），可选 `prompt_engine.optimizer`

旧路径 `platform-orchestrator/services/prompt_service.py` 已废弃。

### 3.2 CLI 子命令

| 命令 | 说明 | 示例 |
|------|------|------|
| classify | 风格分类 | `prompt-engine classify "prompt" -m 5` |
| categories | 列出 25 维 | `prompt-engine categories` |
| optimize | 优化 prompt | `prompt-engine optimize "cat" -p midjourney` |
| recommend | 反向推荐 | `prompt-engine recommend oil_painting` |
| feedback | 反馈查看/提交 | `prompt-engine feedback --stats` |

### 3.3 数据模型

```
PromptBlock (模板引擎)
  ├── name, template (f-string)
  ├── params (参数池, 随机选择)
  └── weight: float

PromptTemplate (组合模板)
  ├── blocks: list[PromptBlock]
  ├── separator, style_categories
  └── render(creative_level=1-10)

StyleCategory (枚举, 25 维)
  ├── Group 视觉风格: design_styles, digital, experimental
  ├── Group 材质: lighting, material_properties, materials, dimensionality
  ├── Group 色彩: colors_and_palettes, combinations
  ├── Group 镜头: camera, perspective, structural_modification
  ├── Group 生物: nature_and_animals, objects, outer_space
  ├── Group 形态: geometry, geography_and_culture
  ├── Group 媒介: drawing_and_art_mediums, sfx_and_shaders
  ├── Group 主题: themes, intangibles, tv_and_movies, song_lyrics
  └── Group 杂项: emojis, miscellaneous

StyleType (枚举, 14 种)
  realistic, cartoon, anime, oil_painting, watercolor, pixel,
  cyberpunk, fantasy, photography, 3d_render, minimalist,
  abstract, portrait, landscape

StyleCategoryResult
  ├── categories: list[StyleCategory]      # 多标签结果
  ├── keywords_found: dict[str, list[str]] # 匹配到的关键词
  ├── method: "keyword_match"|"vector_rag"|"llm_classify"
  └── confidence: float                    # 0.0-1.0

FeedbackEntry
  ├── prompt, detected_categories, corrected_categories
  ├── rating: int 0-5
  ├── method, confidence: float
  └── timestamp, notes
```

---

## 4. 竞争壁垒（技术优势）

### 4.1 三级流水线 vs 单次 LLM 调用

```
传统做法:
  prompt → LLM("分类这个prompt") → 结果
  ❌ 每个请求 1-3 秒
  ❌ 每调用都消耗 tokens
  ❌ LLM 不可用时完全不可用

我们的做法:
  prompt → keyword_match (0ms, 离线)
         → vector_rag (50ms, 离线)
         → llm_classify (1s, 在线兜底)
  ✅ 90%+ 请求在 50ms 内返回
  ✅ LLM 不可用时仍可离线分类
  ✅ kw+vector 零 tokens 消耗
```

### 4.2 反馈闭环 vs 无学习能力

```
竞品:
  classify("cat") → [nature_and_animals]  (每次都相同)
  用户无法纠错, 无法改进
  
我们:
  classify("cat") → [nature_and_animals, lighting]
  用户反馈 "lighting 不对"
  → _apply_feedback()
  → 下次 classify("cat") → [nature_and_animals]  (权重自动修正)
  → 越用越准
```

### 4.3 跨平台一致性

```
同一"风格感知注入"引擎:
  midjourney:   "cat, Golden Hour, --ar 16:9 --v 6.1"
  stable_diff:  "cat, Golden Hour, (masterpiece:1.2)"
  dalle:        "A cat bathed in golden hour light..."
  tongyi:       "一只沐浴在金色阳光中的猫..."
  
✅ 风格维度统一: 都是 Golden Hour (Lighting 类别)
✅ 输出格式各异: 各平台的最佳语法
```

---

## 5. 测试覆盖

| 测试模块 | 用例数 | 说明 |
|----------|--------|------|
| 分类器 | 30 | keyword_match, vector_rag, LLM, 边界, RAG, 反向推荐 |
| 策略 | 18 | 7 平台 system_prompt + post_process |
| 策略集成 | 14 | 端到端集成测试 |
| 故事板 | 46 | StoryboardStrategy ABC + xiaohei 三步隐喻 + REST 端点 |
| A/B 候选 | 3 | 单/多候选 |
| 批量 | 3 | 批量优化 |
| 配置 | 2 | 配置加载 |
| Infinity | 5 | 扩写/扰动/比特级 |
| 逆向 | 2 | 逆向工程 |
| MJ 风格注入 | 3 | 关键词注入 |
| 反馈 | 6 | 存储/统计/持久化 |
| 权重 | 4 | 权重加载/保存/应用 |
| 模板加载 | 6 | 模板加载/回退/变量 |
| 供应商 | 6 | Gemini provider + 注册表 |
| 评估 | 8 | 评估维度/结果/函数 |
| DSL 解析器 | 12 | 变体/通配符/数量限定/嵌套 |
| 看板 API | 4 | 统计端点测试 |
| gpt4o 数据 | 4 |
| 资源/预览/模型 | 9 | 资源展示+图片预览+模型清单 | 1050 案例解析+注入 |
| **合计** | **270** | 全部 mock 隔离, ~25s |

---

## 6. 项目迭代

| 阶段 | 内容 | 交付物 |
|------|------|--------|
| s1 | 竞品分析 | MJ 数据源调研 |
| s2 | MJ 数据库集成 | `mj_style_final.json`, `_inject_style_keywords()` |
| s3 | 分类器 | `StyleCategoryClassifier`, `_keyword_match()` |
| s4 | API | REST + MCP endpoints |
| s5 | 感知注入 | 分类→注入全链路 |
| P0 | 跨平台 | `keyword_injector.py` 共享模块 |
| P1 | RAG + 反向推荐 | `_vector_search()`, `recommend_categories_for_style()` |
| P2 | CLI + README | `cli.py`, 文档 |
| F1 | Agent Skill 分发 | `agents/skills/prompt-engine/` |
| F2 | RAG 种子注入 | 506 GPT-Image2 案例 → 向量库 |
| F3 | Prompt-as-Code 模板 | `template_engine.py` |
| F4 | 模板驱动优化 | `templates/prompts/` YAML 模板系统 |
| F5 | 多模型供应商 | `llm/gemini.py`, `list_providers()` |
| F6 | 评估对比 | `evaluator.py`, `POST /v1/evaluate` |
| P3 | 反馈循环 | `FeedbackStore`, API, CLI |
| P4 | 权重系统 | `keyword_weights.json`, `_apply_feedback_to_weights()` |
| F7 | 外部 RAG 种子 | awesome-gpt-image-2 (506) + gpt4o-image-prompts (1050) |
| F8 | DSL 模板语法 | `dsl_parser.py`, `{a|b}`, `__wild__`, `{N$$opt}` |
| F9 | Web 看板 | Vue 3 + Element Plus, `web/index.html`, 统计 API |
| F10 | 资源展示 | `/v1/resources` 端点, 引擎资产全展示 |
| F11 | 图片预览 | `/v1/preview` + `/v1/image-models`, Pollinations 免费 |
| F12 | 模型 API 配置 | Settings 面板, 6 供应商环境变量 |
| F13 | 小黑分镜策略 | 46 测试 ALL GREEN: ABC 注册表 + xiaohei 三步隐喻 + REST `/v1/storyboard/*` |

---

## 7. 风险与限制

| 风险 | 影响 | 缓解 |
|------|------|------|
| MJ 数据库不更新 | 关键词过时 | 用户反馈权重可补偿 |
| TF-IDF 中文精度 | 不如 embedding | 预留 embedding 接口 |
| 反馈数据稀疏 | 权重效果有限 | 默认 1.0 安全回退 |
| sklearn 依赖 | 安装体积增加 | 缺失时静默降级 |
| BitwiseClassifier 未集成 | 比特级分类未用 | 当前三级流水线足够 |


---

## 八、平台优先级矩阵

> **背景**：原 PRD 列出 6 大平台但未明确优先级，且文心一格已下线需标注。

### 8.1 平台支持状态

| 平台 | 优先级 | 状态 | 策略文件 | 备注 |
|------|--------|------|----------|------|
| **Midjourney** | P0 | 可用 | `midjourney` | 主力平台，参数映射最完善（--ar/--s/--v） |
| **Stable Diffusion** | P0 | 可用 | `stable_diffusion` | 权重语法支持（masterpiece:1.2） |
| **DALL-E** | P1 | 可用 | `dalle` | 自然语言段落式 prompt |
| **通义万相** | P1 | 可用 | `tongyi` | 中文描写，阿里云 API |
| **即梦** | P2 | 可用 | `jimeng` | 视觉冲击力导向 |
| **文心一格** | — | **已下线** | `yizhang`（保留） | 百度已于 2026 年 5 月下线该产品，策略文件保留但不再维护 |
| **通用（Generic）** | P3 | 可用 | `generic` | 不适配特定平台时的兜底模板 |

### 8.2 平台选路规则

1. 用户指定平台 → 直接匹配策略文件
2. 用户未指定 → 按 `MJ > SD > DALL-E > 通义 > 即梦` 顺序，取第一个可用
3. 所有平台策略不可用 → 降级到 `generic` 通用模板
4. 文心一格相关请求 → 自动路由到 `generic` 并记录 warning 日志

### 8.3 策略文件版本要求

每个平台策略文件必须包含：
- `platform_name`: 平台标识
- `system_prompt`: 系统提示词模板
- `post_processor`: 后处理函数（可选）
- `supported_params`: 支持的参数列表
- `status`: `active` | `deprecated` | `experimental`

---

## 九、"小黑分镜"业务定位

> **背景**：F13 迭代新增了"小黑分镜"策略，但业务定位模糊，需明确。

### 9.1 定位声明

**"小黑分镜"** 是 prompt-engine 的 **视频分镜提示词生成模块**，定位如下：

- **核心功能**：将文本内容转换为适用于 AI 视频生成的分镜提示词序列
- **目标场景**：短视频制作、图文转视频、内容二次创作
- **与主线的关系**：独立于图片 prompt 优化流水线，但复用分类器和注入引擎

### 9.2 三步隐喻流程

| 步骤 | 名称 | 输入 | 输出 | 说明 |
|------|------|------|------|------|
| Step 1 | **场景提取** | 文本段落 | 场景列表 | 识别叙事结构，提取关键场景 |
| Step 2 | **视觉隐喻** | 场景列表 | 视觉描述 | 每个场景转换为画面描述（风格、构图、光影） |
| Step 3 | **提示词合成** | 视觉描述 | 分镜 prompt 序列 | 按时间轴组织，含转场提示 |

### 9.3 接口定义

```
POST /v1/storyboard/optimize
POST /v1/storyboard/classify
GET  /v1/storyboard/templates
```

### 9.4 与 content-aggregator 的集成

小黑分镜通过 `PromptEngineExporter`（smart-sentence-splitter v0.6.1+）接收分句结果，自动生成分镜提示词。

---

## 十、LLM 调用成本预算

> **背景**：原 PRD 无成本控制机制，存在无限调用风险。

### 10.1 成本预算矩阵

| 用途 | 模型 | 单次调用成本 | 日均调用量 | 日成本 | 月成本 |
|------|------|-------------|-----------|--------|--------|
| 分类兜底（llm_classify） | GPT-4o-mini | ~0.001 CNY | 100 次 | 0.1 CNY | 3 CNY |
| 优化改写（optimize） | DeepSeek-V3 | ~0.01 CNY | 200 次 | 2 CNY | 60 CNY |
| 逆向工程（reverse_engineer） | GPT-4o | ~0.05 CNY | 50 次 | 2.5 CNY | 75 CNY |
| 小黑分镜 | DeepSeek-V3 | ~0.02 CNY | 100 次 | 2 CNY | 60 CNY |
| **合计** | — | — | — | **6.6 CNY** | **198 CNY** |

### 10.2 成本控制机制

| 机制 | 阈值 | 行为 |
|------|------|------|
| **单用户日限额** | 50 次 LLM 调用/天 | 超限返回 HTTP 429 + `X-RateLimit-Reset` 头 |
| **全局日预算** | 100 CNY/天 | 触发后仅保留 P0 平台（MJ/SD）的优化能力 |
| **月预算上限** | 200 CNY/月 | 触发后暂停逆向工程功能，仅保留分类+优化 |
| **单次 token 上限** | 2000 output tokens | 超限截断并记录 warning |
| **超时熔断** | 连续 3 次超时 | 自动禁用该 provider 10 分钟 |

### 10.3 成本监控

- 每次 LLM 调用记录到 `llm_usage_log` 表：`model, tokens_in, tokens_out, cost_estimate, timestamp`
- 日报自动生成：`GET /v1/ops/cost-report`（需 admin 权限）
- 超预算通知：通过 orchestrator 的告警通道发送

---

## 十一、API 认证机制

### 11.1 认证方式

| 端点类别 | 认证方式 | 说明 |
|----------|----------|------|
| `/v1/optimize`, `/v1/classify` | API Key（Header） | `Authorization: Bearer <API_KEY>` |
| `/v1/storyboard/*` | API Key（Header） | 同上 |
| `/v1/ops/*` | JWT Token | 需要 admin 角色 |
| `/v1/feedback` | 可选 API Key | 匿名反馈允许，绑定 API Key 可追溯 |
| `/v1/health` | 无需认证 | 健康检查端点 |

### 11.2 API Key 管理

- **生成**: 通过 `POST /v1/admin/api-keys` 生成（需 admin JWT）
- **格式**: `pe_` 前缀 + 32 位随机字符串
- **存储**: SHA-256 哈希后存入数据库，原始 Key 仅在生成时返回一次
- **轮换**: 支持手动轮换，旧 Key 有 24h 宽限期
- **撤销**: `DELETE /v1/admin/api-keys/{key_id}`

### 11.3 与系统集成

prompt-engine 作为 gstack 子模块，通过 orchestrator 的 JWT 认证体系接入：
- 用户通过 orchestrator SSO 登录后获取 JWT
- 调用 prompt-engine 时携带 JWT，由 orchestrator 签发
- prompt-engine 验证 JWT 签名（共享密钥 `PO_SECRET_KEY`）

---

## 十二、文案分句 → 提示词 → 生图对比验证（v0.22.0）

> **定位**：一个前端界面，核心目的是**验证图片提示词实际生成的图片效果**。
> 输入一篇文案 → 分句模型分句 → 每句经 MiniMax 生成英文生图提示词 → 同一提示词生成 2 张图片并排对比。

### 12.1 功能目标

1. 文本输入框输入文案，**最多 6000 字**；
2. 调用分句模型（smart-sentence-splitter）分句，**展示具体分句结果**；
3. 每个分句经 MiniMax 多模态模型（文字推理）生成图片提示词；
4. **同一提示词每次生成 2 张图片**进行对比；
5. 可设置模型 API：**仅需输入 MiniMax API Key** 即可完成文字推理与图片生成（base_url / LLM 模型 / 尺寸 / 数量为高级可选项）。

### 12.2 外部契约（复用 Multi-Publish 运营后台设置）

| 能力 | 调用方式 | 说明 |
|------|----------|------|
| 文字推理（LLM） | `POST {base_url}/chat/completions`（OpenAI 兼容） | `base_url` 默认 `https://api.minimaxi.com/v1`；`Authorization: Bearer {key}`；模型默认 `MiniMax-M3`；响应需剥离 `<think>...</think>` 推理块 |
| 图片生成 | `POST {base_url}/image_generation`（同步） | 请求体 `{"model":"image-01","prompt","response_format":"url","n":2,"aspect_ratio":"1:1"}`；响应 `data.image_urls[]`；HTTP 200 但空图必须显式报错 |
| 分句 | `POST {SPLITTER_BASE_URL}/v1/split` | `SPLITTER_BASE_URL` 默认 `http://127.0.0.1:8002`；请求 `{text, language:"auto", mode:"balanced"}`；响应 `sentences[]`（index/text/language/tier/confidence/char_count） |

### 12.3 后端 API 设计

| 端点 | 方法 | 请求 | 响应 | 错误 |
|------|------|------|------|------|
| `/v1/compare/split` | POST | `{text(≤6000), language?, mode?}` | `{sentences[], scenes[], text_length, language, tier_used, splitter, duration_ms}` | 422 空/超长/空结果；503/504 分句服务不可用/超时 |
| `/v1/compare/prompt` | POST | `{text, api_key?, base_url?, model?}` | `{prompt, model, duration_ms, retryable}` | 400 无 key/鉴权失败；429 限流；502 LLM 失败/剥离后为空 |
| `/v1/compare/images` | POST | `{prompt(≤2000), api_key?, base_url?, n(1-4，默认2), width?, height?}` | `{urls[], count, model, duration_ms, retryable}` | 400 无 key/鉴权失败；422 空结果/内容安全/参数非法；429 限流；504 超时；502 其他 |
| `/v1/compare/status` | GET | — | `{has_env_key, splitter, default_llm_model}` | — |

**安全约束**：
- `api_key` 流转：请求体 > 环境变量 `MINIMAX_API_KEY`；只存请求局部变量，不落服务端磁盘、不进服务端日志、不写入服务端存储（前端 localStorage 仅限本机单用户工具场景，见 12.4）；
- `base_url` 覆盖仅允许 `https://host[/path]`（拒绝回环/私网/链路本地/云 metadata 地址，非回环强制 https；SSRF 缓解），默认 `https://api.minimaxi.com/v1`；
- 分句服务 target 由服务端 `SPLITTER_BASE_URL` 固定配置，**不接受前端传入**（防 SSRF）；
- 生图数量上限 4（需求默认 2）。

### 12.4 前端界面（「对比验证」页签）

| 区域 | 显示项 | 交互 |
|------|--------|------|
| ① 文案输入 | 多行文本框、字数统计（`{{n}}/6000`）、清空按钮 | 输入实时计数；超出 6000 字由 `maxlength` 与后端双重拦截 |
| ② MiniMax 模型设置 | API Key（password 型，遮罩显示 `sk****xxxx`）、测试连接按钮、高级设置折叠（Base URL / LLM 模型 / 尺寸 1:1|16:9|9:16|4:3 / 每提示词生成数） | Key 保存到浏览器 localStorage（本地单机工具），随请求发送；「测试连接」调用 `/v1/compare/prompt` 轻量探测 |
| ③ 分句结果 | 每句卡片：序号、字数、tier 标签、置信度百分比、原文；「生成提示词」「生图对比」「复制原文」按钮 | 分句完成后展示；可单独生成提示词/图片；>30 句提示生图成本 |
| ④ 提示词 | 英文生图提示词（可编辑 textarea）、模型名、复制按钮 | 生成中骨架屏；失败显示错误 + 可重试；编辑后可重新生图 |
| ⑤ 双图对比 | 图 1 / 图 2 并排（img），放大弹窗、复制 URL、生成耗时、尺寸 | 「生图对比」触发 n=2；仅 1 张时提示；失败显示错误 + 重试按钮 |
| 汇总操作 | 「生成全部提示词（N）」「生成全部图片（N）」 | 串行执行；>30 句/批量生图前弹确认框（成本提示） |

**状态机（每句独立）**：`idle → loading → done | error`（promptState 与 imageState 各自独立，互不阻塞）。

**提示文字清单**：
- 无 Key：`请先在「MiniMax 模型设置」填写 API Key（或配置环境变量 MINIMAX_API_KEY）`
- 分句服务未启动：`无法连接分句服务 http://127.0.0.1:8002，请先启动 smart-sentence-splitter（端口 8002）`
- 文案超长：`文案超过 6000 字上限`
- 生图进行中：`图片生成中（通常 10~60 秒/张），请耐心等待…`
- 仅 1 张图：`⚠️ 仅返回 1 张图（MiniMax 偶发少图），可点击「重新生图」。`
- 内容安全拒绝：`MiniMax 内容安全策略拒绝了本次生成，请调整提示词后重试`
- 空结果：`MiniMax 返回了空结果（HTTP 200 但无图片 URL），请重试；若反复出现请检查提示词`
- 鉴权失败：`MiniMax 鉴权失败（HTTP 401/403）：请检查 API Key 是否正确`
- 批量确认：`将生成 N 个提示词 x 每张 M 图 = <b>N×M 张图片</b>，会消耗 MiniMax API 额度。继续？`

### 12.5 数据校验

| 字段 | 规则 |
|------|------|
| 文案 text | 非空（去首尾空白）；≤6000 字（按字符数）；超出返回 422 |
| 分句文本 | 非空；>0 句，否则 422 |
| 提示词 prompt | 非空；≤2000 字符；LLM 剥离 `<think>` 后为空视为可重试错误（502） |
| API Key | 非空（请求体或环境变量）；空返回 400 |
| base_url | 仅 `http(s)://host[/path]`；非法返回 422 |
| n | 整数 1~4；默认 2 |
| width/height | 64~4096 像素；默认 1024 |

### 12.6 错误分级（前端可据此提示"可重试"）

| 类型 | 触发 | 可重试 | HTTP |
|------|------|--------|------|
| auth | 401/403 | 否 | 400 |
| invalid_config | 参数非法/无 key | 否 | 400/422 |
| content_safety | 内容安全策略拒绝 | 否 | 422 |
| empty_result | HTTP 200 但无图 | 是 | 422 |
| rate_limit | 429 | 是 | 429 |
| timeout | 超时 | 是 | 504 |
| network / provider_error | 网络/服务端 5xx | 是 | 502/503 |

### 12.7 成本控制

- 批量生图前强制确认（弹窗展示 N×M 图数量）；
- 分句 >30 句时展示成本提示（建议按句选择性生成）；
- 生图数量上限 4；LLM `max_tokens=1500`（预留推理空间，避免整段只有 `<think>`）；
- 图片 URL 仅会话内展示，不落库（Non-goal）。

### 12.8 Non-goals（不做）

- 不做账号体系/多用户；不落库生成历史；
- 不改 smart-sentence-splitter / Multi-Publish 代码；
- 不引入前端构建链（沿用 CDN Vue3 + Element Plus 单页模式）。

### 12.9 测试覆盖

`tests/test_compare_api.py`（17 例，全部 mock 隔离）：
- split：空文本/超长 422、代理成功（url/body 断言）、服务不可用 503、空结果 422；
- prompt：无 key 400、`<think>` 剥离、剥离后为空 502；
- images：无 key 400、双图成功、空结果 422、鉴权 400；
- minimax_client：aspect_ratio 解析、无 key/invalid n/空结果/auth 错误分级。
