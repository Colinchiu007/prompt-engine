# ARCH-F2: 506 案例注入 RAG 种子方案

## 目标

从 awesome-gpt-image-2 的 `data/cases.json`（506 个 GPT-Image2 案例）中提取 prompt 数据，转化为 prompt-engine 的 RAG 知识库种子数据。

## 数据映射

```
awesome-gpt-image-2 cases.json         →  prompt-engine PromptEntry
─────────────────────────────────────────────────────────────
id (string)                            →  id
title (string)                         →  title
prompt (string)                        →  prompt_text
category (Architecture/Brand/etc)      →  categories[0]
styles (["3D", "Illustration", ...])   →  categories[1..n]
scenes (["Commerce", "Creative"])      →  categories[n+1..]
image (URL)                            →  description (含图片链接)
sourceUrl                              →  id + source prefix
```

## 执行步骤

1. 读取 awesome-gpt-image-2 的 `cases.json`（已 clone 到 `research/` 目录）
2. 提取每个案例的 prompt 文本 + 元数据
3. 转换为 `PromptEntry` 对象
4. 调用 `PromptVectorStore.add_prompts()` 写入 RAG 知识库
5. 验证检索：搜索几个关键词确认数据已索引

## 核心代码（单次执行脚本）

```python
from prompt_engine.knowledge.loader import PromptEntry
from prompt_engine.knowledge.vector_store import PromptVectorStore
import json

# 加载 cases.json
with open("path/to/cases.json") as f:
    data = json.load(f)

# 转换
entries = []
for case in data["cases"]:
    entry = PromptEntry(
        id=f"gptimg2-{case['id']}",
        title=case.get("title", ""),
        prompt_text=case.get("prompt", ""),
        categories=[case.get("category", "")] + case.get("styles", []),
        platform="generic",
        quality_score=8,  # GPT-Image2 案例质量较高
    )
    entries.append(entry)

# 写入 RAG
store = PromptVectorStore("./prompts_db")
store.add_prompts(entries)
```

## 测试

- 加载后 query 3 个关键词验证检索结果
- 确认向量索引重建成功（store.count > 500）
