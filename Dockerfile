FROM python:3.12-slim AS builder

WORKDIR /app

# 复制依赖文件
COPY requirements.txt .

# 安装依赖到虚拟环境，减少镜像大小
RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --no-cache-dir --upgrade pip && \
    /opt/venv/bin/pip install --no-cache-dir -r requirements.txt && \
    find /opt/venv -name "*.pyc" -delete && \
    find /opt/venv -name "__pycache__" -delete

# 使用更小的运行时镜像
FROM python:3.12-slim

WORKDIR /app

# 从构建阶段复制虚拟环境
COPY --from=builder /opt/venv /opt/venv

# 设置环境变量使用虚拟环境
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# 复制项目文件，只复制必要的文件
COPY bot.py discord_bot.py kook.py main.py message_forwarder.py translator.py steam_monitor.py forward_config.py cleanup.py ./

# 创建下载目录
RUN mkdir -p downloads/images downloads/videos && \
    apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# 启动命令
CMD ["python", "bot.py"]