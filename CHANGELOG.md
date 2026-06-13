# Changelog

本项目更新日志。

## [Unreleased]

### 新增 (v0.4.0)

- **`rewrite()`** — 借鉴 Infinity `prompt_rewriter.py`，将简短描述扩展为详细 prompt（含 CFG 参数自动判断）
- **`disturb_and_optimize()`** — 借鉴 Infinity BSC，prompt 扰动增强后多次优化取最佳
- **`BitwiseClassifier`** — 借鉴 Infinity IVC，N 分类拆为 d 个二分类，参数量从 O(N×H) 降到 O(d×H)
- **REST API** — 新增 `POST /v1/rewrite` 和 `POST /v1/disturb-optimize` 端点
- **测试** — 新增 16 个测试用例，全量 70 个

### 变更

- `models.py` — 新增 `RewriteRequest` 数据模型
- `__init__.py` — 导出 `RewriteRequest`
- 策略文件数：7 → 7（无变化，策略重写已在 v0.3.1 完成）

-

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
