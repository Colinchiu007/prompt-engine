# ── Build stage ───────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app

# 单独装依赖（利用 Docker 缓存）
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# ── Runtime stage ─────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# 拷贝已安装的依赖
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# 拷贝源码
COPY . .

# 创建数据目录（持久化卷）
RUN mkdir -p /app/prompt_engine/data

# 暴露端口
EXPOSE 8000

# 启动 uvicorn
CMD ["python", "-m", "uvicorn", "prompt_engine.api.rest:app", "--host", "0.0.0.0", "--port", "8000"]
