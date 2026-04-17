# SmartDB-Doc 软件原理与技术架构

## 1. 核心架构
SmartDB-Doc 是一个基于 **Streamlit** 构建的轻量级数据库文档自动化工具。其核心逻辑分为三个层次：

| 层次 | 技术栈 | 功能描述 |
| :--- | :--- | :--- |
| **表现层** | Streamlit | 提供响应式的 Web 界面，处理用户输入和结果展示。 |
| **逻辑层** | SQLAlchemy / oracledb / yasdb | 负责与不同类型的数据库建立连接，提取表结构、字段、索引及样本数据。 |
| **增强层** | OpenAI API (Ollama / DeepSeek) | 利用大语言模型 (LLM) 对原始元数据进行语义分析，推断业务含义。 |

## 2. 关键技术原理

### 2.1 数据库元数据提取
系统使用 **SQLAlchemy Inspector** 接口实现跨数据库的元数据提取。
- **Oracle**: 通过 `oracledb` 驱动连接，查询 `USER_TAB_COLUMNS` 等系统视图。
- **YashanDB**: 针对国产崖山数据库进行了深度适配，支持其特有的系统视图查询。
- **样本采样**: 通过 `SELECT * FROM table WHERE ROWNUM <= 5` (Oracle) 或 `LIMIT 5` (MySQL/PG) 获取真实数据，辅助 AI 理解字段含义。

### 2.2 AI 增强解析
系统将提取的 JSON 格式元数据封装进精心设计的 **Prompt** 中：
1. **上下文注入**: 将表名、字段名、类型、现有备注及样本数据发送给 LLM。
2. **结构化输出**: 要求 LLM 返回固定格式的 JSON，包含 `business_name` 和 `columns_explanation`。
3. **本地化支持**: 支持通过 **Ollama** 调用本地运行的 `qwen2.5:14b` 等模型，确保数据隐私。

### 2.3 文档自动化生成
- **Markdown**: 实时生成符合 GitHub 规范的文档，并集成 **Mermaid** 渲染 ER 图。
- **Word (Docx)**: 使用 `python-docx` 库将解析结果转换为企业级报表格式。

---

## 3. 常见问题排查 (Troubleshooting)

### 3.1 连接拒绝 (Connection Refused / Errno 111)
**现象**: 报错 `DPY-6005: cannot connect to database ... [Errno 111] Connection refused`。

**原因分析**:
当 SmartDB-Doc 运行在 Docker 容器中时，`localhost` 指向的是**容器内部**。如果您的 Oracle 数据库运行在宿主机或其他容器中，SmartDB-Doc 无法通过 `localhost` 找到它。

**解决方案**:
1. **连接宿主机数据库**: 
   - 使用宿主机的真实 IP 地址（如 `192.168.1.x`）。
   - 或者在 Linux 宿主机上使用 Docker 特殊域名：`host.docker.internal` (需在 `docker-compose.yml` 中配置 `extra_hosts`)。
2. **连接另一个 Docker 容器**:
   - 确保两个容器在同一个 Docker 网络中。
   - 使用目标容器的 `container_name` 作为 Host。

### 3.2 Oracle 驱动问题
**现象**: 报错 `DPI-1047: Cannot locate a 64-bit Oracle Client library`。

**解决方案**:
- 本项目已在 Dockerfile 中集成了 `libaio1`。
- 对于 Oracle 11g 等老版本，建议在 `db_utils.py` 中切换为 **Thin Mode** (默认已优先尝试 Thin Mode)。

### 3.3 AI 解析超时
**现象**: 批量解析时进度条卡住。

**解决方案**:
- 检查 Ollama 是否已启动：`curl http://localhost:11434/v1/models`。
- 确保宿主机防火墙允许容器访问 Ollama 端口（通常是 11434）。
