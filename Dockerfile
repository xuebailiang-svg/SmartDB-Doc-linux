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
# 使用通配符 COPY，支持任意版本的 instantclient-*.zip
COPY instantclient-*.zip /opt/oracle/
RUN cd /opt/oracle && \
    unzip instantclient-*.zip && \
    rm -f instantclient-*.zip && \
    # 动态寻找解压后的目录名 (通常以 instantclient_ 开头)
    ORACLE_INSTANT_CLIENT_DIR=$(find /opt/oracle -maxdepth 1 -type d -name "instantclient_*" | head -n 1) && \
    echo "Found Oracle Instant Client at: $ORACLE_INSTANT_CLIENT_DIR" && \
    echo $ORACLE_INSTANT_CLIENT_DIR > /etc/ld.so.conf.d/oracle-instantclient.conf && \
    ldconfig && \
    # 将路径保存到环境变量文件中，方便后续使用
    echo "export LD_LIBRARY_PATH=$ORACLE_INSTANT_CLIENT_DIR:\$LD_LIBRARY_PATH" >> /etc/profile

# 设置 Oracle 相关的环境变量
# 注意：由于 ENV 不支持动态 shell 命令，我们通过 ldconfig 已经解决了库加载问题
# NLS_LANG 依然保持 UTF-8 预设
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
