# ARCH-F1: 引擎资源展示

## 目标

Dashboard 顶部展示 prompt-engine 内嵌的全部资产，让用户对引擎能力一目了然。

## 设计

### 端点

```
GET /v1/resources
```

### 返回结构

```json
{
  "platforms": 7,
  "platform_list": ["midjourney", "stable-diffusion", ...],
  "rag_cases": 936,
  "mj_keywords": 2100,
  "style_dimensions": 25,
  "llm_providers": 3,
  "wildcards": 100,
  "templates": 2
}
```

### 资源清单

| 资源 | 数量 | 数据来源 |
|------|------|---------|
| 平台策略 | 7 | 硬编码列表 |
| RAG 案例 | 936 | `prompts_db/prompts.json` (918) + `knowledge/seed_prompts.json` (18) |
| MJ 关键词 | 2100 | `data/mj_style_final.json`（25 维 × 84 词/维） |
| 风格维度 | 25 | 硬编码（与 models.py 一致） |
| LLM 供应商 | 3 | 硬编码 |
| DSL 通配符 | 100+ | `templates/wildcards.yaml`（10 类 × 10 值） |
| 模板 | 2 | `templates/prompts/` 目录 |

## 实现

```python
@app.get("/v1/resources")
async def engine_resources():
    # 1. 平台硬编码
    platforms = ["midjourney", "stable-diffusion", "dall-e", ...]
    
    # 2. RAG 案例：扫描多个路径
    rag_paths = [base / "prompts_db" / "prompts.json",
                 base / "knowledge" / "seed_prompts.json"]
    rag_cases = sum_file_list_length(rag_paths)
    
    # 3. MJ 关键词：解析 mj_style_final.json
    mj_count = count_keys_in_dict(base / "data" / "mj_style_final.json")
    
    # 4. 通配符：解析 wildcards.yaml
    wildcards_count = count_yaml_list_values(base / "templates" / "wildcards.yaml")
    
    return {...}
```

## 前端展示

Dashboard 顶部新卡片，3 列布局：

```
┌──────────────┬──────────────┬──────────────┐
│ 平台策略 7   │ RAG 936      │ LLM 3        │
│ 7 个标签     │ MJ 关键词 2100│ 通配符 100   │
│              │              │ 模板 2       │
└──────────────┴──────────────┴──────────────┘
```

## 决策

- **路径扫描**而非硬编码数量：保证真实反映数据
- **多路径回退**：RAG 数据可能在 prompts_db / knowledge / data 不同位置
- **降级到默认值**：找不到时返回已知的合理估计（如 MJ 关键词 2100）
