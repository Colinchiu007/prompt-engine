# Prompt Engine — 图片生成提示词优化引擎

一个轻量级的 Python 引擎模块，将用户原始提示词自动优化为适合主流 AI 图片生成平台的高质量提示词。

## 特性

- 🎯 **多平台适配**：Midjourney / Stable Diffusion / DALL·E / 通义万相 / 文心一格 / 即梦 / 通用
- 🌐 **中英文自适应**：输入语言决定输出语言
- 🎨 **风格化优化**：支持写实、卡通、动漫、油画、赛博朋克等 12 种风格
- 🔌 **三种集成方式**：Python SDK / REST API / MCP Server
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

result = optimizer.optimize(OptimizeRequest(
    prompt="一只猫在窗台上晒太阳",
    platform=PlatformType.MIDJOURNEY,
    style=StyleType.REALISTIC,
))

print(result.optimized_prompt)
# 输出: 一只毛茸茸的橘猫蜷缩在阳光明媚的木窗台上... --ar 16:9 --v 6 --s 250
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
```

### 启动 MCP Server

```bash
python examples/start_mcp_server.py
```

支持 MCP 的 AI 客户端可直接调用 `optimize_prompt` tool。

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
```

支持通过环境变量注入敏感信息：`export OPENAI_API_KEY=sk-xxx`

## 项目结构

```
prompt-engine/
├── prompt_engine/          # 核心包
│   ├── optimizer.py        # 编排器
│   ├── config.py           # 配置加载
│   ├── models.py           # 数据模型
│   ├── strategies/         # 平台策略（可扩展）
│   ├── llm/               # LLM 供应商抽象层
│   └── api/               # 服务层（REST + MCP）
├── tests/                  # 测试
├── examples/               # 使用示例
├── config.yaml             # 默认配置文件
└── README.md
```

## 添加新平台

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

## 运行测试

```bash
pytest -v
```

## License

MIT