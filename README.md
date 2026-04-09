# SmartDB-Doc-linux 🚀

SmartDB-Doc 的 Linux 优化版，专为 Linux 服务器和 Docker 部署设计。

## 🌟 主要改进
- **Docker 支持**：提供 `Dockerfile` 和 `docker-compose.yml`，一键容器化部署。
- **YashanDB 增强**：针对 YashanDB 23.4+ 版本优化了元数据提取逻辑，使用 Oracle 兼容视图。
- **Linux 依赖优化**：预配置了 Linux 下所需的系统库支持。

## 🛠️ 部署方式

### 方式一：使用 Docker (推荐)
1. 克隆仓库：
   ```bash
   git clone https://github.com/xuebailiang-svg/SmartDB-Doc-linux.git
   cd SmartDB-Doc-linux
   ```
2. 启动容器：
   ```bash
   docker-compose up -d
   ```
3. 访问：`http://your-server-ip:8501`

### 方式二：直接在 Linux 运行
1. 安装依赖：
   ```bash
   pip install -r requirements.txt
   ```
2. 启动应用：
   ```bash
   streamlit run app.py
   ```

## 🔌 支持的数据库
- **YashanDB** (针对 23.4+ 优化)
- **MySQL**
- **PostgreSQL**
- **Oracle**
- **SQL Server**

## 📄 许可证
MIT License
