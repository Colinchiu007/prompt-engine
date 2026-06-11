# Prompt Engine — 图片生成提示词优化引擎

一个轻量级的 Python 引擎模块，将用户原始提示词自动优化为适合主流 AI 图片生成平台的高质量提示词。支持正向优化和逆向工程。

## 特性

- 🎯 **多平台适配**：Midjourney / Stable Diffusion / DALL·E / 通义万相 / 文心一格 / 即梦 / 通用
- 🌐 **中英文自适应**：输入语言决定输出语言
- 🎨 **风格化优化**：支持写实、卡通、动漫、油画、赛博朋克等 12 种风格
- 🔙 **逆向工程**：从图片 URL 分析生成对应平台的提示词（视觉模型）
- 🔀 **A/B 多候选**：一次生成多个不同创意的优化版本
- 📦 **批量优化**：一次请求处理最多 10 条提示词
- 🔌 **三种集成方式**：Python SDK / REST API / MCP Server
- 📚 **RAG 增强**：基于知识库检索相似优质提示词，提升生成质量
- 🔄 **可扩展架构**：新增平台 = 一个策略文件，新增 LLM 供应商 = 一个 Provider 文件

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

# 图片逆向工程
from prompt_engine import ReverseRequest
result = optimizer.reverse_engineer(ReverseRequest(
    image_url="https://example.com/photo.jpg",
    platform=PlatformType.MIDJOURNEY,
))
print(result.prompt)
print(result.description)  # 图片描述文本
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

### 查询平台 `GET /v1/platforms`

返回所有支持的平台及其配置。

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
│   ├── optimizer.py        # 编排器（optimize + reverse_engineer + A/B）
│   ├── config.py           # 配置加载 + 环境变量解析
│   ├── models.py           # 数据模型
│   ├── strategies/         # 平台策略（可扩展）
│   ├── llm/               # LLM 供应商抽象层
│   ├── api/               # 服务层（REST + MCP）
│   ├── knowledge/         # RAG 知识库
│   ├── templates/         # 风格模板引擎
│   ├── prompts_db/        # 优质提示词数据库
│   └── image/             # 图片分析（逆向工程）
├── tests/                  # 测试（40 个用例，100% mock 隔离）
├── examples/               # 使用示例
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

全部 40 个测试通过，使用 mock 隔离，无需真实 API Key。

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

### 后续对接计划

| 阶段 | 任务 | 负责人 |
|------|------|--------|
| Phase 2 | **RAG 基础设施**（ChromaDB/嵌入/检索API集成到optimizer） | **开发会话** |
| Phase 2 | RAG 质量调优（top_k/阈值/混合检索策略） | COO/运营 |
| Phase 2 | 风格模板库 seeds.yaml（基于 NBP 分类提取） | COO/运营 |

### 数据来源

- [Nano Banana Pro Prompts](https://github.com/YouMind-OpenLab/awesome-nano-banana-pro-prompts) — 14,292 条社区高质量 prompt，16 语言，42 个分类
- 详细变更见 [CHANGELOG.md](CHANGELOG.md)

## 版本历史

- **v0.1.0** — 初始版本：基础优化、多平台适配、三种集成方式
- **v0.2.0** — P1 功能：negative_prompt、模板引擎 styles.yaml、批量优化
- **v0.3.0** — P2 功能：RAG 知识库增强、A/B 多候选、图片逆向工程
- **v0.3.1** — 策略重写：基于 Nano Banana Pro (14,000+ prompts) 社区 prompt 提取各平台最佳模式，7 个策略文件全面增强（Midjourney 参数映射/SD 权重语法/DALL·E 自然语言结构/通义万相中文描写/文心一格关键词式/即梦视觉冲击力），镜头术语/光照分类/颜色精度/构图技巧全部内化为策略规则

## License

MIT
