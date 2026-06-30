---
name: prompt-engine-design
description: prompt-engine DESIGN.md — 架构决策与设计原理
---

# Prompt Engine — 设计文档

> **版本**: v0.19.1 | **更新**: 2026-07-01
> **关联**: docs/PRD.md, docs/ARCHITECTURE.md

## 一、分类管线设计

### 1.1 三阶段分类（顺序不可逆）

```
用户输入
   │
   ├── 1. keyword_match（~0.1ms）
   │   正则关键词匹配 → 预定义 25 StyleCategory
   │   命中低延迟风格 → 直接输出，不走后续阶段
   │
   ├── 2. vector_rag（~50ms）
   │   ChromaDB 语义检索 + TF-IDF 关键词召回
   │   RAG 双通道融合 → 精确分类 + 模板匹配
   │
   └── 3. llm_classify（~500ms）
       LLM 调用进行语义分类
       仅当前两阶段置信度 < 阈值时触发
```

**关键约束**：三阶段顺序不可互换。keyword_match 最快但最精确（命中即确定）；vector_rag 次快但需要索引；llm_classify 最慢但有最广的覆盖。

### 1.2 Fast Path vs Precise Path

| 路径 | 触发条件 | 耗时 | 输出 |
|------|---------|------|------|
| Fast Path | creative_level ≤ 3 | ~1ms | 模板直接输出 |
| Precise Path | creative_level ≥ 4 | ~1-3s | RAG + LLM 优化 |

---

## 二、缓存设计

### 2.1 双层缓存

| 层级 | 实现 | 容量 | TTL | 场景 |
|------|------|------|-----|------|
| L1 | MemoryCache (LRU) | 1024 条 | 5min | 高吞吐重复请求 |
| L2 | SQLite 持久化 | 无限制 | 24h | 跨进程/持久化 |

### 2.2 写入策略

```
查询 → L1 命中 → 返回
   ↓ (miss)
查询 → L2 命中 → 回填 L1 → 返回
   ↓ (miss)
查询 → 完整管线 → 写入 L1+L2 → 返回
```

### 2.3 失效策略

- L1 过期：TTL 到期或 LRU 淘汰
- L2 过期：TTL 到期或手动 clear_cache()
- 写穿透：新结果同时写入 L1+L2

---

## 三、平台策略架构

### 3.1 BaseStrategy 抽象

```python
class BaseStrategy(ABC):
    platform: str          # "weibo", "douyin", "bilibili" 等
    style_category: StyleCategory

    @abstractmethod
    def generate_prompt(self, context: PromptContext) -> str: ...
    @abstractmethod
    def parse_response(self, response: str) -> PromptResult: ...
```

### 3.2 7 平台实现

| 平台 | 策略类 | 提示词特色 |
|------|--------|-----------|
| 微博 | WeiboStrategy | 短文本，话题标签 |
| 抖音 | DouyinStrategy | 口语化，节奏感 |
| B站 | BilibiliStrategy | 弹幕互动，分段标题 |
| 小红书 | XiaohongshuStrategy | 种草风格，emojis |
| 知乎 | ZhihuStrategy | 深度分析，结构化 |
| 公众号 | WechatStrategy | 长文，排版标记 |
| YouTube | YouTubeStrategy | SEO 关键词，章节标记 |

---

## 四、RAG 设计

### 4.1 双通道检索

| 通道 | 引擎 | 优势 | 劣势 |
|------|------|------|------|
| 语义 | ChromaDB (sentence-transformers) | 理解意图 | 需 GPU/量化 |
| 关键词 | TF-IDF (sklearn) | 精确匹配 | 无法理解语义 |

### 4.2 种子库

- 100+ 人工标注提示词种子
- 覆盖全部 7 平台 × 25 StyleCategory
- 定期自动扩展（高质量生成结果回注）

---

## 五、性能约束

| 指标 | 目标 | 测量方式 |
|------|------|---------|
| Fast Path | <5ms | pytest-benchmark |
| Precise Path | <3s | 集成测试 |
| 缓存命中率 | >70% | cache stats API |
| RAG 检索 | <100ms | 索引优化监控 |

---

## 六、向后兼容

- 外部导入 `from prompt_engine import Optimizer` 接口不变
- 新增模块通过 `__getattr__` 懒加载，不增加主模块启动耗时
- 25 StyleCategory enum 不可变（可扩展不可删改）
