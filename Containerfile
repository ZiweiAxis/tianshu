# E11-S1：天枢容器化构建（Podman/Docker 兼容）
FROM python:3.12-slim

WORKDIR /app

# 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 应用
COPY src ./src
COPY main.py ./
COPY .env.example .env.example

# 健康探针默认端口（可被覆盖）
ENV HEALTH_PORT=8080

# 主进程：桥接 + 健康端点（同进程）；从项目根运行
CMD ["python", "main.py"]
