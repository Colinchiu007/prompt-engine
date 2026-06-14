# Prompt Engine 用户手册

一个轻量级的 Python 引擎模块和 Web 工具，将简短的文字描述自动优化为适配主流 AI 图片生成平台的高质量提示词。

- **版本**：v0.13.0
- **测试**：212 个全部通过
- **部署**：`docker-compose up`
- **源码**：[github.com/Colinchiu007/prompt-engine](https://github.com/Colinchiu007/prompt-engine)

---

## 目录

1. [快速开始](#1-快速开始)
2. [Web 界面使用指南](#2-web-界面使用指南)
3. [CLI 使用指南](#3-cli-使用指南)
4. [API 使用指南](#4-api-使用指南)
5. [高级功能](#5-高级功能)
6. [部署指南](#6-部署指南)
7. [常见问题](#7-常见问题)

---

## 1. 快速开始

### 方式一：Docker（推荐）

```bash
git clone https://github.com/Colinchiu007/prompt-engine.git
cd prompt-engine
docker-compose up -d
# 打开 http://localhost:8000
```

### 方式二：本地运行

```bash
git clone https://github.com/Colinchiu007/prompt-engine.git
cd prompt-engine
pip install -r requirements.txt
python -m uvicorn prompt_engine.api.rest:app --port 8000
# 打开 http://localhost:8000
```

### 方式三：CLI 直接使用

```bash
# 优化一个 prompt
python -m prompt_engine.cli optimize --prompt "a cat" --platform midjourney

# 风格分类
python -m prompt_engine.cli classify --prompt "a majestic cat"
```

### 配置 LLM（可选但推荐）

在项目根目录创建 `.env` 文件：

```
OPENAI_API_KEY=sk-...
```

如不配置，优化/分类/评估功能会返回错误。图片预览（Picsum）无需任何 Key。

---

## 2. Web 界面使用指南

打开 http://localhost:8000/ 后，顶部有三个标签页：

### 2.1 Prompt 工作台

这是核心页面。包含以下功能区域：

#### ① 模式切换

顶部有「单条」和「批量」两个模式按钮。

**单条模式**（默认）：
- 在文本框输入描述，如 `a majestic cat sitting on a velvet throne`
- 选择平台（Midjourney / Stable Diffusion / DALL·E 等）
- 选择风格（可选，不选则自动检测）
- 点击「优化 Prompt」→ 右侧显示优化结果
- 点击「风格分类」→ 显示分类结果
- 点击「评估对比」→ 显示 5 维度评分

**批量模式**：
- 每行输入一个 prompt（最多 10 行）
- 点击「批量优化」
- 每条结果独立显示，可单独复制

#### ② 扩写

输入简短的描述（如 `a cat`），点击「扩写」按钮，自动扩写到 300 词。扩写结果可一键「填入输入框」继续优化。

#### ③ A/B 多版本

点击「A/B 多版本」按钮，系统会对 prompt 做同义词替换和词序打乱，生成 3 个不同版本并排对比。默认选中最佳版本，可「选用」或「复制」。

#### ④ 优化结果

优化完成后，下方显示：
- **原始输入**：你输入的文本
- **优化结果**：优化后的 prompt（可复制）
- **平台标签**：当前平台
- **耗时**：优化用时
- **👍 满意 / 👎 不满意**：提交反馈（影响后续权重）

#### ⑤ 图片预览

优化完成后，选择模型（默认 Picsum Photos，完全免费），点击「生成预览」。实时显示预览图。

#### ⑥ 示例

页面下方有 5 个快捷示例和 4 组分类示例（风景/人物/科幻/动物），点击自动填入。

### 2.2 数据看板

点击「数据看板」标签，展示：

**统计卡片**（4 张）：
- 总请求数
- 成功率
- 平均耗时
- 错误数

**引擎资源**：
- 7 个平台策略
- 936 条 RAG 案例库
- 2057 个 MJ 关键词
- 25 个风格维度
- 3 个 LLM 供应商
- DSL 通配符池
- 模板文件

**分类分布**（饼图）：各风格维度被分类的次数占比

**平台分布**（柱状图）：各平台被调用的次数对比

> 首次打开时统计卡片有 50 条演示数据（自动填充），使用后替换为真实数据。

### 2.3 配置

点击「配置」标签，展示：

**LLM 供应商**：切换 OpenAI / 讯飞星火 / Gemini（切换后重启服务）

**DSL 通配符池**：查看 10 类通配符池

**平台策略**：7 个平台的策略说明（MJ 参数映射、SD 权重语法等）

**图片生成模型**：16 个预设模型，标记免费/需 Key

**API Key 配置**：6 个供应商的环境变量说明

---

## 3. CLI 使用指南

### 安装

```bash
# 从源码（pip 发布前）
git clone https://github.com/Colinchiu007/prompt-engine.git
cd prompt-engine
pip install -e .
```

### 命令

```bash
# 优化 prompt
prompt-engine optimize --prompt "a cat" --platform midjourney

# 风格分类
prompt-engine classify --prompt "a majestic cat in golden lighting"

# 列出所有风格维度
prompt-engine categories

# 提交反馈
prompt-engine feedback --prompt "a cat" --result "A majestic feline..."

# 获取推荐
prompt-engine recommend --prompt "a cat"
```

### 参数说明

| 命令 | 参数 | 说明 |
|------|------|------|
| optimize | `--prompt` | 输入文本（必填） |
| | `--platform` | 目标平台（默认 midjourney） |
| | `--style` | 风格（可选） |
| | `--creative-level` | 创意等级 1-10（默认 7） |
| | `--max-length` | 最大长度（默认 500） |
| classify | `--prompt` | 输入文本（必填） |
| categories | 无 | 列出所有风格 |

---

## 4. API 使用指南

### 基础 URL

```
http://localhost:8000
```

### 完整端点

| 方法 | 路径 | 说明 |
|------|------|------|
| **POST** | `/v1/optimize` | **优化 prompt** |
| **POST** | `/v1/optimize/batch` | 批量优化 |
| **POST** | `/v1/classify` | 风格分类 |
| **POST** | `/v1/evaluate` | 评估对比 |
| **POST** | `/v1/rewrite` | 扩写 prompt |
| **POST** | `/v1/disturb-optimize` | 扰动增强 |
| **POST** | `/v1/feedback` | 提交反馈 |
| **POST** | `/v1/feedback/apply` | 应用反馈到权重 |
| **GET** | `/v1/stats/overview` | 看板统计 |
| **GET** | `/v1/stats/categories` | 分类分布 |
| **GET** | `/v1/stats/platforms` | 平台分布 |
| **GET** | `/v1/resources` | 引擎资源 |
| **GET** | `/v1/keywords` | 平台关键词 |
| **GET** | `/v1/styles/categories` | 风格维度 |
| **GET** | `/v1/image-models` | 图片模型 |
| **POST** | `/v1/preview` | 图片预览 |
| **GET** | `/v1/platforms` | 平台列表 |

### 常用示例

```python
import requests

# 1. 优化 prompt
resp = requests.post("http://localhost:8000/v1/optimize", json={
    "prompt": "a majestic cat",
    "platform": "midjourney",
    "style": "fantasy",  # 可选
    "creative_level": 7,
    "max_length": 500
})
data = resp.json()
print("优化结果：", data["optimized_prompt"])
print("耗时：", data["duration_ms"], "ms")

# 2. 风格分类
resp = requests.post("http://localhost:8000/v1/classify", json={
    "prompt": "a majestic cat"
})
print("分类：", resp.json()["categories"])

# 3. 扩写
resp = requests.post("http://localhost:8000/v1/rewrite", json={
    "prompt": "a cat",
    "platform": "midjourney",
    "max_length": 300
})
print("扩写：", resp.json()["optimized_prompt"])

# 4. 批量优化
resp = requests.post("http://localhost:8000/v1/optimize/batch", json={
    "requests": [
        {"prompt": "a cat", "platform": "midjourney"},
        {"prompt": "cyberpunk city", "platform": "midjourney"}
    ]
})
print("批量结果：", [r["optimized_prompt"][:50] for r in resp.json()])

# 5. 提交反馈
resp = requests.post("http://localhost:8000/v1/feedback", json={
    "entry_type": "positive",
    "prompt": "a cat",
    "optimized_prompt": "A majestic feline...",
    "platform": "midjourney"
})
print("反馈已提交")

# 6. 图片预览（Picsum 免费）
resp = requests.post("http://localhost:8000/v1/preview", json={
    "prompt": "a majestic cat",
    "model": "picsum"
})
print("图片 URL：", resp.json()["url"])
```

---

## 5. 高级功能

### 5.1 RAG 知识库

当启用 RAG（默认启用）时，优化引擎会自动检索相似历史 prompt 案例作为 few-shot 参考注入系统提示词。知识库包含：

- **awesome-gpt-image-2** 的 506 条案例
- **gpt4o-image-prompts** 的 1050 条双语案例

RAG 检索使用 Chroma 向量数据库。当 `sklearn` 未安装时自动降级为关键词匹配。

### 5.2 反馈闭环

每次优化后，你可以点击「👍 满意」或「👎 不满意」提交反馈。这些反馈会：

1. 存储在 `feedback_db.json` 中
2. 在 Settings 页面查看统计
3. 点击「应用反馈」后调整关键词权重

反馈越多，分类器越精准。

### 5.3 缓存池

相同 prompt + 相同平台 + 相同参数的请求，第二次起直接返回缓存结果（0ms，0 tokens）。

缓存 key 包含：
- prompt（模糊匹配，相似度 ≥ 0.7）
- platform
- creative_level
- max_length
- negative_prompt
- num_candidates

### 5.4 风格注入

所有 7 个平台策略都支持 MJ 风格关键词注入。优化时，25 维 MJ 风格分类器会自动检测 prompt 的风格，然后向优化结果中注入对应平台格式的关键词。

---

## 6. 部署指南

### 6.1 Docker（生产推荐）

```bash
# 构建并启动
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止
docker-compose down

# 带 LLM Key 启动
OPENAI_API_KEY=sk-... docker-compose up -d
```

### 6.2 手动部署

```bash
# 安装依赖
pip install -r requirements.txt
pip install playwright
playwright install chromium

# 启动
uvicorn prompt_engine.api.rest:app --host 0.0.0.0 --port 8000

# 后台运行
nohup uvicorn prompt_engine.api.rest:app --host 0.0.0.0 --port 8000 &
```

### 6.3 环境变量

| 变量 | 说明 | 必需 |
|------|------|------|
| `OPENAI_API_KEY` | OpenAI API Key | 优化/分类/评估 |
| `XFYUN_APPID` | 讯飞星火 APPID | 讯飞供应商 |
| `XFYUN_API_KEY` | 讯飞星火 API Key | 讯飞供应商 |
| `GEMINI_API_KEY` | Gemini API Key | Gemini 供应商 |
| `LLM_PROVIDER` | 供应商名（默认 xfyun） | 否 |

### 6.4 测试

```bash
# 全量测试
pytest tests/ -q

# 只看失败
pytest tests/ -q --tb=line

# E2E 测试（需先启动服务）
pytest tests/test_web_e2e.py -v
```

---

## 7. 常见问题

### Q: 为什么优化结果为空？

A: 请确认 LLM API Key 已配置。日志中如有 `401 Unauthorized` 说明 Key 无效。如无 Key，优化会返回 502。

### Q: 为什么图片预览失败？

A: 默认 Picsum 完全免费，无需 Key。如果失败，检查网络是否能访问 `picsum.photos`。其他模型需在 Settings 页面配置对应 API Key。

### Q: 数据看板为什么是 0？

A: 首次打开时有 50 条演示数据。如果仍是 0，检查浏览器 Console 是否有错误（F12 → Console）。

### Q: 怎么添加新的平台？

A: 在 `prompt_engine/strategies/` 下创建新策略文件，实现 `build_system_prompt()` 和 `post_process()` 方法，然后在 `__init__.py` 中注册。

### Q: 数据存储在哪儿？

| 数据 | 存储位置 |
|------|---------|
| 反馈数据 | `feedback_db.json` |
| 关键词权重 | `keyword_weights.json` |
| RAG 向量库 | `prompts_db/chroma.sqlite3` |
| RAG 案例 | `prompts_db/prompts.json` |
| 统计数据 | 内存（重启重置） |

### Q: 如何备份/迁移？

备份 `prompt_engine/prompts_db/` 和 `prompt_engine/data/` 目录即可。重启服务后自动加载。

---

*文档版本 v0.13.0 / 2026-06-13*
