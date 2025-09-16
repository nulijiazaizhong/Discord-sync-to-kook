FROM python:3.12-slim

WORKDIR /app

# 复制依赖文件
COPY requirements.txt .

# 安装依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目文件
COPY . .

# 创建下载目录
RUN mkdir -p downloads/images downloads/videos

# 设置环境变量
ENV PYTHONUNBUFFERED=1

# 启动命令
CMD ["python", "bot.py"]