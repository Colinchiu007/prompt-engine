# Prompt Engine — 图片生成提示词优化引擎

一个轻量级的 Python 引擎模块，将用户原始提示词自动优化为适合主流 AI 图片生成平台的高质量提示词。支持正向优化、逆向工程和 prompt 扩写。

## 特性

- 🎯 **多平台适配**：Midjourney / Stable Diffusion / DALL·E / 通义万相 / 文心一格 / 即梦 / 通用
- 🌐 **中英文自适应**：输入语言决定输出语言
- 🎨 **风格化优化**：支持写实、卡通、动漫、油画、赛博朋克等 14 种风格
- 🔙 **逆向工程**：从图片 URL 分析生成对应平台的提示词（视觉模型）
- 🔀 **A/B 多候选**：一次生成多个不同创意的优化版本
- 📦 **批量优化**：一次请求处理最多 10 条提示词
- 🔌 **三种集成方式**：Python SDK / REST API / MCP Server
- 📚 **RAG 增强**：基于知识库检索相似优质提示词，提升生成质量
- 🔄 **可扩展架构**：新增平台 = 一个策略文件，新增 LLM 供应商 = 一个 Provider 文件
- ✍️ **Prompt 扩写**：借鉴 Infinity 项目，将简短描述自动扩展为详细图像生成提示词（含 CFG 参数）
- 🎲 **扰动增强优化**：借鉴 Infinity BSC，对 prompt 做同义词替换和词序打乱，多版本择优
- 🧠 **比特级分类器**：借鉴 Infinity IVC，大类别分类参数量降低 20 倍以上
- 🏷️ **25 维风格分类**：基于 MJ Style Reference 的 25 维度风格分类器（关键词 + 向量语义 + LLM 三级流水线）
- 🔍 **CLI 工具**：命令行直接运行风格分类、列出维度、优化 prompt
- 🌍 **跨平台风格注入**：所有 7 个平台策略均支持 MJ 风格关键词注入
- 🤖 **Agent Skill 分发**：导出为 Claude / Cursor / Hermes 可安装的 Agent Skill（`npm run install:skill`）
- 🧩 **Prompt-as-Code 模板**：原子化 PromptBlock + 组合模板引擎，低创意等级纯模板渲染不调 LLM
- 📋 **模板驱动优化**：策略 LLM 指令抽取为独立 YAML 模板，EN/ZH 双语支持
- 🏢 **多模型供应商**：支持 OpenAI / 讯飞 / Gemini 等供应商，统一注册表
- 📊 **评估对比**：5 维度 LLM 评估优化效果（clarity/specificity/creativity/actionability/platform_best）
- 🗂️ **多源 RAG 种子**：集成 awesome-gpt-image-2 (506)、gpt4o-image-prompts (1050) 等外部案例库
- 📚 **资源展示**：Dashboard 完整展示引擎所有资源（数据/词库/供应商/通配符/模板）
- 🔤 **DSL 模板语法**：`{option1|option2}` / `__wildcard__` / `{N$$opt}` 模板语法，借鉴 sd-dynamic-prompts
- 🖼️ **图片预览**：Workbench 内置 14 个图片生成模型预览，Pollinations 免费
- 🖥️ **Web 看板**：Vue 3 + Element Plus 全功能界面（Prompt 工作台 / 数据看板 / 配置面板）：`{option1|option2}` / `__wildcard__` / `{N$$opt}` 模板语法，借鉴 sd-dynamic-prompts

## 25 维 MJ 风格分类体系

基于 MidJourney Styles Reference 的 25 个风格维度，覆盖光照/材质/色彩/镜头/构图/自然/艺术媒介/文化风格/影视参考/特效：

| 维度 | 中文名 | 说明 | 示例关键词 |

### 分类三级流水线

```
prompt → keyword_match (0ms, 精确命中)
          ↓ (置信度 < 0.6)
       vector_rag (50ms, TF-IDF 语义搜索)
          ↓ (无结果)
       llm_classify (1s, 零样本分类)
```

90%+ 请求在 **50ms 内**返回结果，仅兜底路径需要 LLM 调用。

### 反馈闭环

```
用户提交纠正 → feedback_db.json → prompt-engine feedback --apply
                                      ↓
                               keyword_weights.json 更新
                                      ↓
                               下次分类自动使用新权重
```

越用越准——用户只需提交评分和纠正即可。

|------|--------|------|-----------|
| `lighting` | 光照效果 | 光线类型、照明方式、阴影 | Volumetric Lighting, Rembrandt, God Rays |
| `material_properties` | 材质属性 | 表面质感、透明度、反射 | Glossy, Translucent, Refractive |
| `materials` | 材料 | 具体材质的视觉呈现 | Concrete, Metal, Wood, Marble |
| `dimensionality` | 维度感 | 2D/3D/2.5D 空间深度 | Isometric, Flat, Parallax |
| `colors_and_palettes` | 色彩与调色板 | 色调方案、色彩搭配 | Pastel, Monochrome, Vibrant |
| `combinations` | 组合效果 | 特殊色彩组合、发光材质 | Iridescent, Pearl, Neon |
| `camera` | 摄影与镜头 | 相机类型、焦段、拍摄技法 | Macro, Wide Angle, Tilt-Shift |
| `perspective` | 视角与构图 | 透视角度、构图方式 | Bird's Eye, Worm's Eye, Dutch Angle |
| `structural_modification` | 结构修改 | 变形、扭曲、抽象 | Warped, Spiral, Möbius |
| `nature_and_animals` | 自然与动物 | 风景、植物、动物、生态 | Golden Retriever, Aurora, Meadow |
| `objects` | 物体与道具 | 日常物品、机械、电子 | Vaporwave Cassette, Tesla Coil |
| `outer_space` | 太空与宇宙 | 星空、星球、星云 | Nebula, Galaxy, Solar Eclipse |
| `geometry` | 几何形状 | 图案、多面体、对称 | Sacred Geometry, Fractal, Tessellation |
| `geography_and_culture` | 地理与文化 | 地域风格、民族特色、历史 | Chinese Ink, Japanese, Egyptian |
| `drawing_and_art_mediums` | 绘画与艺术媒介 | 画种、技法、艺术形式 | Watercolor, Oil, Charcoal, Ink |
| `sfx_and_shaders` | 特效与着色器 | 视觉特效、后期处理 | Ray Tracing, Bloom, Chromatic Aberration |
| `themes` | 主题与氛围 | 情绪概念、美学运动 | Cyberpunk, Steampunk, Gothic |
| `intangibles` | 抽象概念 | 不可见的事物、能量 | Consciousness, Quantum, Aura |
| `tv_and_movies` | 影视参考 | 电影/动画风格 | Studio Ghibli, Noir, IMAX |
| `song_lyrics` | 音乐与歌词 | 音乐风格视觉化 | Synthwave, Lo-fi, Ambient |
| `design_styles` | 设计风格 | 艺术运动、设计流派 | Art Deco, Bauhaus, Minimalism |
| `digital` | 数字艺术 | CG、像素、电子游戏 | Pixel Art, Low Poly, Voxel |
| `experimental` | 实验性 | 前卫、概念艺术 | Glitch, Datamosh, Generative |
| `emojis` | Emoji 表情 | 符号、图标风格 | Emoji, Sticker, Icon |
| `miscellaneous` | 杂项 | 特殊渲染效果 | 500x Magnification, X-Ray |

## 快速开始

### 安装

```bash
pip install .
```

### 作为 SDK 使用

```python
from prompt_engine import Optimizer, OptimizeRequest, PlatformType, StyleType

optimizer = Optimizer()

# 正向优化
result = optimizer.optimize(OptimizeRequest(
    prompt="一只猫在窗台上晒太阳",
    platform=PlatformType.MIDJOURNEY,
    style=StyleType.REALISTIC,
))
print(result.optimized_prompt)
# 输出: 一只毛茸茸的橘猫蜷缩在阳光明媚的木窗台上... --ar 16:9 --v 6 --s 250

# A/B 多候选
result = optimizer.optimize(OptimizeRequest(
    prompt="森林小径",
    platform=PlatformType.GENERIC,
    num_variants=3,  # 生成 3 个不同创意版本
))
print(result.variants)  # 返回 [OptimizeResult, OptimizeResult, OptimizeResult]

# 逆向工程
result = optimizer.reverse_engineer(ReverseRequest(
    image_url="https://example.com/photo.jpg",
    platform=PlatformType.MIDJOURNEY,
))
print(result.prompt)
print(result.description)  # 图片描述文本

# Prompt 扩写（灵感: Infinity 项目）— 将简短描述扩展为详细 prompt
from prompt_engine import RewriteRequest
result = optimizer.rewrite(RewriteRequest(
    prompt="a tree",
    platform=PlatformType.GENERIC,
))
print(result.optimized_prompt)
# 输出: A majestic oak tree stands proudly in a sunlit meadow, its branches stretching out like welcoming arms...

# 扰动增强优化 — 多版本择优
result = optimizer.disturb_and_optimize(OptimizeRequest(
    prompt="forest morning",
    platform=PlatformType.MIDJOURNEY,
    creative_level=8,
))
print(result.optimized_prompt)
print(result.candidates)  # 扰动后的备选版本
```

### 命令行工具

```bash
# 风格分类
prompt-engine classify "A serene landscape bathed in golden light" -m 5

# JSON 格式输出
prompt-engine classify "cyberpunk city neon lights" --json

# 列出所有 25 个风格维度
prompt-engine categories

# 优化 prompt
prompt-engine optimize "a cat" -p midjourney -c 7
```

### 启动 REST API

```bash
python examples/start_rest_server.py
```

```bash
# 调用示例
curl -X POST http://localhost:8013/v1/optimize \
  -H "Content-Type: application/json" \
  -d '{"prompt": "a cat", "platform": "midjourney", "creative_level": 7}'

# 逆向工程
curl -X POST http://localhost:8013/v1/reverse \
  -H "Content-Type: application/json" \
  -d '{"image_url": "https://example.com/photo.jpg", "platform": "midjourney"}'
```

### 启动 MCP Server

```bash
python examples/start_mcp_server.py
```

支持 MCP 的 AI 客户端可直接调用 `optimize_prompt` 和 `reverse_prompt` 两个工具。

## API 文档

### 正向优化 `POST /v1/optimize`

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| prompt | string | ✅ | - | 用户原始提示词 |
| platform | string | ❌ | "generic" | 目标平台 |
| style | string | ❌ | "realistic" | 艺术风格 |
| creative_level | int | ❌ | 5 | 创意度 1-10 |
| negative_prompt | string | ❌ | "" | 负面提示词 |
| num_variants | int | ❌ | 1 | 生成版本数 (1-3) |
| max_length | int | ❌ | 500 | 输出最大长度 |

### 逆向工程 `POST /v1/reverse`

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| image_url | string | ✅ | - | 图片 URL |
| platform | string | ❌ | "generic" | 目标平台 |
| style | string | ❌ | - | 艺术风格 |
| detail | string | ❌ | "auto" | 视觉分析详细度: low/auto/high |

### 批量优化 `POST /v1/batch`

一次请求最多 10 条优化任务，返回结果数组。

### 风格分类反馈 `POST /v1/feedback`

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| prompt | string | ✅ | - | 被分类的 prompt |
| detected_categories | string[] | ❌ | [] | 检测到的类别 |
| corrected_categories | string[] | ❌ | [] | 纠正后的类别 |
| rating | int | ❌ | 0 | 评分 0-5 |
| method | string | ❌ | "" | 分类方法 |
| confidence | float | ❌ | 0.0 | 置信度 |

### 反馈统计 `GET /v1/feedback/stats`

返回总反馈数、平均评分、方法分布等统计。

### 应用反馈权重 `POST /v1/feedback/apply`

应用所有未处理的反馈数据，调整关键词权重。后续分类自动使用新权重。

### Query platforms `GET /v1/platforms`

Returns all supported platforms and their config.

### Style classification `POST /v1/classify`

Analyze a prompt and return its MJ style dimensions.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| prompt | string | ✅ | - | Prompt to classify |
| max_categories | int | ❌ | 5 | Max categories to return |
| use_llm | bool | ❌ | true | Use LLM if keyword match is low |

### List style categories `GET /v1/styles/categories`

Return all 25 MJ style dimensions with Chinese names.

### Prompt rewrite `POST /v1/rewrite`

灵感来自 Infinity 项目，将简短描述自动扩展为详细的图像生成提示词。

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| prompt | string | ✅ | - | 原始简短描述 |
| platform | string | ❌ | "generic" | 目标平台 |
| max_length | int | ❌ | 500 | 输出最大长度 |

### 扰动增强优化 `POST /v1/disturb-optimize`

对 prompt 做扰动增强后多次优化，返回最佳结果。

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| prompt | string | ✅ | - | 原始提示词 |
| platform | string | ❌ | "generic" | 目标平台 |
| strength | float | ❌ | 0.3 | 扰动强度 (0.0-1.0) |
| num_augmented | int | ❌ | 3 | 增强版本数 |

## 配置

编辑 `config.yaml`：

```yaml
llm:
  provider: openai_compat          # 供应商: openai_compat | xfyun
  openai_compat:
    api_key: "${OPENAI_API_KEY}"   # API Key（支持环境变量）
    base_url: "https://api.openai.com/v1"
    model: "gpt-4o"
    temperature: 0.7
    max_tokens: 500
    timeout: 60
  xfyun:
    api_key: "${XFYUN_API_KEY}"
    base_url: "https://maas-coding-api.cn-huabei-1.xf-yun.com/v2"
    model: "astron-code-latest"
    temperature: 0.7
    max_tokens: 500
    timeout: 60

engine:
  default_platform: generic
  default_style: realistic
  max_retries: 2

# 知识库（RAG）配置
knowledge:
  enabled: true
  embedding:
    model: "text-embedding-3-small"
  persist_dir: "./prompts_db"
  retrieval:
    top_k: 3
    min_score: 0.3

# 平台策略配置
platforms:
  midjourney:
    enabled: true
    default_aspect_ratio: "16:9"
    default_version: "6"
  stable_diffusion:
    enabled: true
  dalle:
    enabled: true
  tongyi:
    enabled: true
  yizhang:
    enabled: true
  jimeng:
    enabled: true
  generic:
    enabled: true
```

支持通过环境变量注入敏感信息：`export OPENAI_API_KEY=sk-xxx`

## 项目结构

```
prompt-engine/
├── prompt_engine/          # 核心包
│   ├── optimizer.py        # 编排器（optimize + reverse_engineer + rewrite + disturb_optimize）
│   ├── rewriter.py         # Prompt 扩写器（灵感: Infinity prompt_rewriter）
│   ├── disturb.py          # Prompt 扰动增强（灵感: Infinity BSC）
│   ├── classifier.py       # 比特级分类器（灵感: Infinity IVC）
│   ├── config.py           # 配置加载 + 环境变量解析
│   ├── models.py           # 数据模型
│   ├── strategies/         # 平台策略（可扩展）
│   ├── llm/               # LLM 供应商抽象层
│   ├── api/               # 服务层（REST + MCP）
│   ├── knowledge/         # RAG 知识库
│   ├── keyword_injector.py # MJ 风格关键词注入（跨平台共享）
│   ├── template_engine.py  # Prompt-as-Code 模板引擎
│   ├── cli.py             # 命令行工具
│   ├── templates/         # 风格模板引擎
│   ├── prompts_db/        # 优质提示词数据库
│   └── image/             # 图片分析（逆向工程）
├── tests/                  # 测试（203 个用例，mock 隔离）
├── examples/               # 使用示例
│   ├── sdk_usage.py
│   ├── seed_rag_from_gptimage2.py
│   └── seed_rag_from_gpt4o_prompts.py
├── config.yaml             # 默认配置文件
└── README.md
```

## 扩展开发

### 添加新平台

1. 在 `prompt_engine/strategies/` 下新建 `.py` 文件
2. 继承 `BaseStrategy`，实现 `build_system_prompt` 方法
3. 用 `@register("platform_name")` 装饰器注册
4. 在 `strategies/__init__.py` 中导入

```python
from prompt_engine.strategies.base import BaseStrategy, register

@register("my_platform")
class MyPlatformStrategy(BaseStrategy):
    platform = PlatformType.GENERIC

    @classmethod
    def build_system_prompt(cls, style=None, creative_level=5, max_length=500):
        return f"你是一位 MyPlatform 提示词专家..."
```

### 添加新 LLM 供应商

1. 在 `prompt_engine/llm/` 下新建 provider 文件
2. 实现 `BaseLLMProvider.chat()` 和 `.model_name` 属性
3. 在 `llm/__init__.py` 注册

## 运行测试

```bash
pytest -v
```

全部 203 个测试通过，使用 mock 隔离，无需真实 API Key。

## 开发对接

### 策略文件变更（v0.3.1）

以下是近期策略文件重写对 011 开发会话的影响清单：

| 变更 | 影响范围 | 动作 |
|------|---------|------|
| `strategies/midjourney.py` 全面重写 | build_system_prompt 签名不变 | ✅ 无需改动，向后兼容 |
| `strategies/stable_diffusion.py` 全面重写 | build_system_prompt 签名不变 | ✅ 无需改动，向后兼容 |
| `strategies/dalle.py` 全面重写 | build_system_prompt 签名不变 | ✅ 无需改动，向后兼容 |
| `strategies/tongyi.py` 全面重写 | build_system_prompt 签名不变 | ✅ 无需改动，向后兼容 |
| `strategies/yizhang.py` 全面重写 | build_system_prompt 签名不变 | ✅ 无需改动，向后兼容 |
| `strategies/jimeng.py` 全面重写 | build_system_prompt 签名不变 | ✅ 无需改动，向后兼容 |
| `strategies/generic.py` 全面重写 | build_system_prompt 签名不变 | ✅ 无需改动，向后兼容 |
| `models.py` 新增 PORTRAIT / LANDSCAPE | OptimizeRequest 兼容 | ⚠️ 新增枚举值，老代码不会受影响 |
| `llm/xfyun.py` timeout 15→60 | 配置已更新 | ✅ 无需改动 |

**重要**：所有策略重写均保持 `build_system_prompt(style, creative_level, max_length)` 签名不变，`post_process` 签名不变。对上层 `Optimizer`、`FastAPI`、`MCP Server` **零破坏**。

### 数据来源

- [Nano Banana Pro Prompts](https://github.com/YouMind-OpenLab/awesome-nano-banana-pro-prompts) — 14,292 条社区高质量 prompt，16 语言，42 个分类
- 详细变更见 [CHANGELOG.md](CHANGELOG.md)

## 版本历史

- **v0.1.0** — 初始版本：基础优化、多平台适配、三种集成方式
- **v0.2.0** — P1 功能：negative_prompt、模板引擎 styles.yaml、批量优化
- **v0.3.0** — P2 功能：RAG 知识库增强、A/B 多候选、图片逆向工程
- **v0.3.1** — 策略重写：基于 Nano Banana Pro (14,000+ prompts) 社区 prompt 提取各平台最佳模式，7 个策略文件全面增强（Midjourney 参数映射/SD 权重语法/DALL·E 自然语言结构/通义万相中文描写/文心一格关键词式/即梦视觉冲击力），镜头术语/光照分类/颜色精度/构图技巧全部内化为策略规则
- **v0.5.0** — 25 维 MJ 风格分类器（关键词 + 向量语义 + LLM 三级流水线）、跨平台风格关键词注入、CLI 工具、RAG 增强分类器、反馈闭环、反馈驱动权重调整
- **v0.6.0** — Agent Skill 分发（`agents/skills/prompt-engine`）、RAG 种子注入（506 GPT-Image2 案例）、Prompt-as-Code 模板引擎（`template_engine.py`）
- **v0.7.0** — 模板驱动优化（YAML 模板）、多模型供应商（Gemini）、Web 看板（Vue 3 + Element Plus）
- **v0.9.3** — Dashboard 资源展示、Workbench 图片预览（14 模型）、Settings 图片模型 API 配置、评估对比模式（`POST /v1/evaluate`）、DSL 模板语法（`{a|b}` / `__wild__` / `{N$$opt}`）

## License

MIT
