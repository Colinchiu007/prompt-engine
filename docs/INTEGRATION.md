# Prompt Engine 集成指南

## 概述

5 种集成方式，覆盖所有语言和场景。

| 方式 | 快速通道 | 适合场景 |
|------|---------|---------|
|------|---------|---------|
| **Web 看板** | `python -m uvicorn prompt_engine.api.rest:app` → 浏览器打开 | 可视化操作 |
| **Python SDK** | `pip install prompt-engine` | Python 项目 |
| **REST API** | `python -m uvicorn prompt_engine.api.rest:app` | 任意语言 HTTP 调用 |
| **MCP Server** | `python -m prompt_engine.api.mcp_server` | Claude/Cursor/Hermes |
| **CLI** | `prompt-engine optimize 'text'` | Shell 脚本/CI |
| **Agent Skill** | 复制到 `.hermes/skills/` | Claude Code/Cursor/Hermes |

---

## 1. Python SDK

```bash
pip install prompt-engine
```

```python
from prompt_engine import Optimizer

# 优化 prompt
opt = Optimizer()
result = opt.optimize("a majestic cat in a garden", platform="midjourney")
print(result.prompt)        # 优化后的 prompt
print(result.platform)      # midjourney
print(result.creative_level)  # 创意等级

# 指定平台
opt.optimize("a cat", platform="stable-diffusion")
opt.optimize("a cat", platform="dall-e")
opt.optimize("一只猫", platform="tongyi-wanxiang")

# 风格分类
from prompt_engine import StyleCategoryClassifier
cls = StyleCategoryClassifier()
result = cls.classify("a majestic golden cat")
print(result.category)      # 风格维度
print(result.subcategory)   # 次分类
print(result.confidence)    # 置信度

# 评估对比
from prompt_engine.evaluator import evaluate_prompt
result = evaluate_prompt("original prompt", "optimized prompt")
print(result.dimensions)    # {clarity: 8, specificity: 7, ...}

# DSL 模板
from prompt_engine.dsl_parser import render, register_wildcard_pool
register_wildcard_pool("colors", ["red", "blue", "golden"])
result = render("A {big|small} {cat|dog} in __colors__")
print(result)  # "A big cat in golden"
```

---

## 2. REST API

```bash
# 启动服务
python -m uvicorn prompt_engine.api.rest:app --host 0.0.0.0 --port 8000
```

### 端点一览

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/v1/optimize` | 优化 prompt |
| POST | `/v1/optimize/batch` | 批量优化 |
| POST | `/v1/classify` | 风格分类 |
| GET | `/v1/styles/categories` | 列风格维度 |
| POST | `/v1/evaluate` | 评估对比 |
| POST | `/v1/reverse` | 逆向工程 |
| POST | `/v1/rewrite` | 扩写 prompt |
| POST | `/v1/disturb-optimize` | 扰动增强 |
| POST | `/v1/feedback` | 提交反馈 |
| GET | `/v1/platforms` | 列出平台 |
| GET | `/v1/feedback/stats` | 反馈统计 |
| GET | `/v1/feedback/recent` | 最近反馈 |
| POST | `/v1/feedback/apply` | 应用反馈到权重 |
| GET | `/v1/stats/overview` | 看板概览统计 |
| GET | `/v1/stats/categories` | 看板分类分布 |
| GET | `/v1/stats/platforms` | 看板平台分布 |
| GET | `/v1/resources` | 引擎资源清单（v0.8.0） |
| GET | `/v1/image-models` | 图片模型清单（v0.8.0） |
| POST | `/v1/preview` | AI 图片预览（v0.8.0） |
| GET | `/health` | 健康检查 |

### curl 示例

```bash
# 优化 prompt
curl -X POST http://localhost:8000/v1/optimize \
  -H "Content-Type: application/json" \
  -d '{"prompt": "a majestic cat", "platform": "midjourney"}'

# 风格分类
curl -X POST http://localhost:8000/v1/classify \
  -H "Content-Type: application/json" \
  -d '{"prompt": "a golden sunset over mountains"}'

# 批量优化
curl -X POST http://localhost:8000/v1/optimize/batch \
  -H "Content-Type: application/json" \
  -d '{"prompts": ["cat", "dog", "sunset"], "platform": "midjourney"}'

# 评估对比
curl -X POST http://localhost:8000/v1/evaluate \
  -H "Content-Type: application/json" \
  -d '{"original": "a cat", "optimized": "a majestic feline"}'
```

### 其他语言调用

```javascript
// JavaScript / Node.js
const res = await fetch('http://localhost:8000/v1/optimize', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({prompt: 'a cat', platform: 'midjourney'})
});
const data = await res.json();
console.log(data.prompt);
```

```go
// Go
body := `{"prompt":"a cat","platform":"midjourney"}`
resp, _ := http.Post("http://localhost:8000/v1/optimize", "application/json", strings.NewReader(body))
defer resp.Body.Close()
data, _ := io.ReadAll(resp.Body)
fmt.Println(string(data))
```

```java
// Java (Spring RestTemplate)
RestTemplate rest = new RestTemplate();
Map<String, String> req = Map.of("prompt", "a cat", "platform", "midjourney");
Map resp = rest.postForObject("http://localhost:8000/v1/optimize", req, Map.class);
System.out.println(resp.get("prompt"));
```

---

## 3. MCP Server

### 启动

```bash
python -m prompt_engine.api.mcp_server
```

### 在 Claude Desktop 中使用

编辑 `claude_desktop_config.json`：

```json
{
  "mcpServers": {
    "prompt-engine": {
      "command": "python",
      "args": ["-m", "prompt_engine.api.mcp_server"]
    }
  }
}
```

### 在 Cursor 中使用

设置 → MCP → 添加新服务器：
- **名称**: `prompt-engine`
- **类型**: `command`
- **命令**: `python -m prompt_engine.api.mcp_server`

### 可用 Tools

| Tool | 说明 | 参数 |
|------|------|------|
| `optimize` | 优化 prompt | prompt, platform, creative_level |
| `classify` | 风格分类 | prompt |
| `reverse_engineer` | 逆向工程 | prompt, platform |
| `list_categories` | 列出风格维度 | — |

---

## 4. CLI

```bash
# 优化 prompt
python -m prompt_engine.cli optimize "a majestic cat" --platform midjourney

# 风格分类
python -m prompt_engine.cli classify "a golden sunset"

# 列出风格维度
python -m prompt_engine.cli categories

# 推荐风格
python -m prompt_engine.cli recommend "photorealistic"

# 反馈
python -m prompt_engine.cli feedback --view
python -m prompt_engine.cli feedback --submit "cat" "design_styles" 0.95 --correct "nature"
```

### 安装为全局命令

```bash
# 通过 pip 安装时自动注册
pip install -e .
prompt-engine optimize "a cat" --platform midjourney
```

---

## 5. Agent Skill

### 安装到 Claude Code

```bash
# 复制技能到 Claude Code 目录
cp -r agents/skills/prompt-engine ~/.claude/skills/
```

### 安装到 Cursor

```bash
# 复制到 Cursor 技能目录
cp -r agents/skills/prompt-engine ~/.cursor/skills/
```

### 安装到 Hermes

```bash
# 复制到 Hermes 技能目录
cp -r agents/skills/prompt-engine ~/.hermes/skills/
```

---

## 快速比较：选哪种方式？

| 你的场景 | 推荐方式 |
|---------|---------|
| Python 项目 | Python SDK |
| Node.js / Java / Go / ... 项目 | REST API |
| 想用 AI 工具（Claude/Cursor） | MCP Server |
| Shell 脚本 / CI 流程 | CLI |
| 在 AI 对话中直接用 | Agent Skill |
| 生产环境多服务 | REST API + Docker |

## 测试

207 个测试通过（mock 隔离，无需 API Key）。


## 测试

- 全部 207 个测试通过（mock 隔离，无需 API Key）
- 优化器缓存（v0.9.3）：207 = 207 + 1 cache test
