# ARCH-F5: Dashboard 测试数据种子

## 目标

API 启动时自动填充 50 条模拟记录，确保 Dashboard 首次打开即有数据。

## 设计要点

### 数据模型

```python
# 内存 stats_store 初始化
stats_store = {
    "total_requests": 0,
    "success_rate": 100.0,
    "avg_time_ms": 0,
    "error_count": 0,
    "categories": {},   # name -> count
    "platforms": {},    # name -> count
}
```

### 种子生成策略

- 50 条模拟记录，在启动时一次性写入 stats_store
- 数据分布：
  - platform: 7 个平台均匀分布（~7 条/平台）
  - category: 25 个风格随机加权（digital/design/photo 略高）
  - duration: 正态分布 500-3000ms
  - success: 95%
- 时间戳：过去 24h 均匀分布

### 种子覆盖条件

- 只有 **第一次启动** 时自动 seed
- 已有真实数据时 **不覆盖**
- 可通过 `POST /v1/dev/seed` 手动重新 seed（开发模式）

### 文件改动

```
prompt_engine/api/rest.py        # +seed_data_inspect +main startup hook
tests/test_device.py              # +种子测试
```

## 实现

### 1. seed_data() 函数

```python
def seed_demo_data():
    """启动时自动注入 50 条模拟数据到 stats_store"""
    platforms = [...]
    sample_prompts = [...]
    categories = list(StyleCategory)
    
    for _ in range(50):
        plat = random.choice(platforms)
        cats = random.sample(categories, random.randint(1, 3))
        duration = int(random.gauss(1500, 800))  # 500-3000ms
        
        # 写入 stats_store
        stats_store["total_requests"] += 1
        stats_store["avg_time_ms"] = ...
        for c in cats:
            stats_store["categories"][c] = stats_store.get(...)
        stats_store["platforms"][plat] = stats_store.get(...)
    
    logger.info("Seeded 50 demo records for Dashboard")
```

### 2. 启动钩子

```python
@app.on_event("startup")
async def startup():
    seed_demo_data()
```

### 3. 前端联动

前端已通过 `/v1/stats/overview`, `/v1/stats/categories`, `/v1/stats/platforms` 读取数据，无需修改。