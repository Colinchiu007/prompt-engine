# ARCH-F7: Docker 容器化部署

## 目标

让用户 `docker-compose up` 即可启动整个项目，零本地依赖。

## 设计

### Dockerfile

```dockerfile
# 阶段 1: 构建依赖
FROM python:3.11-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# 阶段 2: 运行
FROM python:3.11-slim
WORKDIR /app
COPY --from=builder /root/.local /root/.local
COPY . .
ENV PATH=/root/.local/bin:$PATH
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "prompt_engine.api.rest:app", "--host", "0.0.0.0", "--port", "8000"]
```

### docker-compose.yml

```yaml
version: '3.8'
services:
  api:
    build: .
    ports: ["8000:8000"]
    environment:
      - LLM_PROVIDER=openai_compat  # 容器内可覆盖
    env_file: .env  # 用户本地 LLM keys
    volumes:
      - ./prompt_engine/data:/app/prompt_engine/data  # 数据持久化
```

### 关键决策

| 决策 | 原因 |
|------|------|
| **多阶段构建** | 减小最终镜像 ~50% |
| **`-slim` 而非 `alpine`** | 兼容性更好（chromaprint 编译等） |
| **`0.0.0.0` 监听** | Docker 容器可外部访问 |
| **数据卷挂载** | RAG 数据集 / 反馈数据持久化 |
| **不预装 LLM Key** | 用户通过 .env 自带（更安全） |

### 镜像大小目标

| 基础镜像 | 大小 |
|----------|------|
| python:3.11 (full) | ~880MB |
| python:3.11-slim | ~150MB |
| python:3.11-alpine | ~50MB (但要编译) |

**选择 slim** — 平衡大小与启动速度。

## 文件结构

```
prompt-engine/
├── Dockerfile                # 新增
├── docker-compose.yml        # 新增
├── .dockerignore             # 新增
└── ...
```

## 测试

- **本地测试**：`docker build .` + `docker run -p 8000:8000`
- **CI 测试**：`docker build --target builder`（验证构建不报错）
