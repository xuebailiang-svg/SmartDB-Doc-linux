# 使用 Python 3.11 稳定版镜像 (Debian 12 bookworm)
FROM python:3.11-slim-bookworm

# 设置工作目录
WORKDIR /app

# 安装系统依赖
# 注意：在 Debian 12 中，libaio1 仍然可用
# 如果在其他版本中需要 libaio1t64，可以通过 || true 来忽略错误
RUN apt-get update && apt-get install -y \
    build-essential \
    libaio1 \
    curl \
    unzip \
    git \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件并安装 Python 包
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目代码
COPY . .

# 暴露 Streamlit 默认端口
EXPOSE 8501

# 设置环境变量
ENV STREAMLIT_SERVER_PORT=8501
ENV STREAMLIT_SERVER_ADDRESS=0.0.0.0

# 启动命令
CMD ["streamlit", "run", "app.py"]
