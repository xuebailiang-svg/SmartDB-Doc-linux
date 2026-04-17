# 使用 Python 3.11 稳定版镜像 (Debian 12 bookworm)
FROM python:3.11-slim-bookworm

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    build-essential \
    libaio1 \
    curl \
    unzip \
    git \
    && apt-get install -y libaio1t64 || true \
    && rm -rf /var/lib/apt/lists/*

# 安装 Oracle Instant Client (开启 Thick Mode 以解决乱码)
# 增加重试逻辑 (--retry 5) 和连接超时设置 (--connect-timeout 30)
RUN mkdir -p /opt/oracle && \
    cd /opt/oracle && \
    curl --retry 5 --retry-delay 5 --connect-timeout 30 -L -o instantclient-basiclite.zip https://download.oracle.com/otn_software/linux/instantclient/211000/instantclient-basiclite-linux.x64-21.10.0.0.0dbru.zip && \
    unzip instantclient-basiclite.zip && \
    rm -f instantclient-basiclite.zip && \
    echo /opt/oracle/instantclient_21_10 > /etc/ld.so.conf.d/oracle-instantclient.conf && \
    ldconfig

# 设置 Oracle 相关的环境变量
ENV LD_LIBRARY_PATH=/opt/oracle/instantclient_21_10:$LD_LIBRARY_PATH
ENV NLS_LANG=AMERICAN_AMERICA.AL32UTF8

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
