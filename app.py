import streamlit as st
import pandas as pd
from db_utils import get_engine, get_schema_metadata
from ai_utils import analyze_table_with_ai, generate_er_diagram_mermaid
import json

st.set_page_config(page_title="SmartDB-Doc", page_icon="🚀", layout="wide")

# 初始化 Session State
if 'metadata' not in st.session_state:
    st.session_state.metadata = []
if 'er_diagram' not in st.session_state:
    st.session_state.er_diagram = ""
if 'api_key' not in st.session_state:
    st.session_state.api_key = ""
if 'base_url' not in st.session_state:
    st.session_state.base_url = "http://host.docker.internal:11434/v1"
if 'model' not in st.session_state:
    st.session_state.model = "qwen2.5:14b"

st.title("🚀 SmartDB-Doc: 全能数据库文档自动化生成工具")

# 侧边栏配置
with st.sidebar:
    st.header("🔌 数据库连接配置")
    db_type = st.selectbox("数据库类型", ["Oracle", "MySQL", "PostgreSQL", "SQL Server", "YashanDB"])
    host = st.text_input("Host", "192.168.1.239")
    port = st.text_input("Port", "1521")
    user = st.text_input("User", "medadm")
    password = st.text_input("Password", type="password")
    database = st.text_input("Service Name / SID / DB Name", "ORCLPDB")
    
    st.divider()
    st.header("🎯 提取范围")
    scope_type = st.radio("提取范围", ["全库", "指定 Schema", "指定表"])
    target_schema = ""
    target_tables = ""
    if scope_type == "指定 Schema":
        target_schema = st.text_input("Schema 名称 (如: HR)")
    elif scope_type == "指定表":
        target_tables = st.text_area("表名 (多个请用逗号分隔)")
    
    enable_sampling = st.checkbox("启用样本数据采样 (前5行)", value=True)
    
    st.divider()
    st.header("🤖 AI 配置")
    model_provider = st.selectbox(
        "模型提供商", 
        ["Ollama (本地)", "OpenAI", "DeepSeek", "其他 (OpenAI 兼容)"],
        index=0 if "11434" in st.session_state.base_url else 1 if "openai" in st.session_state.base_url else 2 if "deepseek" in st.session_state.base_url else 3
    )
    
    # 根据模型提供商选择模型
    if model_provider == "Ollama (本地)":
        model_options = ["qwen2.5:14b", "qwen2.5:7b", "llama3"]
        default_model = "qwen2.5:14b"
        default_base_url = "http://host.docker.internal:11434/v1"
    elif model_provider == "OpenAI":
        model_options = ["gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"]
        default_model = "gpt-4o"
        default_base_url = "https://api.openai.com/v1"
    elif model_provider == "DeepSeek":
        model_options = ["deepseek-chat", "deepseek-coder"]
        default_model = "deepseek-chat"
        default_base_url = "https://api.deepseek.com/v1"
    else:
        model_options = []
        default_model = ""
        default_base_url = ""

    st.session_state.base_url = st.text_input("API Base URL", value=st.session_state.base_url if st.session_state.base_url else default_base_url)
    
    if model_options:
        st.session_state.model = st.selectbox("模型名称", model_options, index=model_options.index(st.session_state.model) if st.session_state.model in model_options else 0)
    else:
        st.session_state.model = st.text_input("模型名称", value=st.session_state.model)
        
    st.session_state.api_key = st.text_input("API Key", value=st.session_state.api_key, type="password")

    if st.button("开始连接并提取元数据", use_container_width=True):
        try:
            with st.status("正在执行元数据提取任务...", expanded=True) as status:
                st.write("正在初始化数据库引擎...")
                engine = get_engine(db_type, host, port, user, password, database)
                
                st.write(f"正在连接 {db_type} 并提取元数据...")
                
                # 定义日志回调
                def log_callback(msg):
                    st.write(msg)

                st.session_state.metadata = get_schema_metadata(
                    engine, 
                    scope_type=scope_type, 
                    target_schema=target_schema if target_schema else None, 
                    target_tables=target_tables,
                    enable_sampling=enable_sampling,
                    log_callback=log_callback
                )
                
                st.write("正在生成 ER 图预览...")
                st.session_state.er_diagram = generate_er_diagram_mermaid(st.session_state.metadata)
                
                status.update(label=f"提取完成！共获取 {len(st.session_state.metadata)} 张表", state="complete", expanded=False)
            
            st.success(f"成功提取 {len(st.session_state.metadata)} 张表的元数据！")
        except Exception as e:
            st.error(f"连接失败: {str(e)}")
            if db_type == "Oracle":
                st.info("提示：如果连接 Oracle 11g 失败，请确保已安装 Oracle Instant Client 并配置 PATH。")
            elif db_type == "SQL Server":
                st.info("提示：请确保已安装 ODBC Driver 17/18 for SQL Server。")
            elif db_type == "YashanDB":
                st.info("提示：请确保已安装 YashanDB Python 驱动 (yasdb)。如果使用 SQLAlchemy 模式，还需安装 yashandb_sqlalchemy 方言库。")
            
            st.warning("💡 容器连接提示：如果数据库在宿主机或其他容器，请勿使用 'localhost'。请尝试使用宿主机 IP 或 Docker 容器名。")

# 主界面展示
if st.session_state.metadata:
    tab1, tab2, tab3 = st.tabs(["📊 元数据预览", "🧠 AI 增强解析", "📄 文档导出"])
    
    with tab1:
        st.subheader(f"{db_type} 表结构预览")
        for table in st.session_state.metadata:
            with st.expander(f"表: {table['table_name']} ({table['table_comment']})"):
                st.markdown("**字段信息**")
                df = pd.DataFrame(table['columns'])
                st.table(df)
                
                if table.get('sample_data'):
                    st.markdown("**样本数据 (前5行)**")
                    sample_df = pd.DataFrame(table['sample_data'])
                    st.dataframe(sample_df)
    
    with tab2:
        st.subheader("AI 增强业务解析")
        st.info("AI 将根据表名、字段名、备注及样本数据，自动推断业务含义并生成详细描述。")
        
        if st.button("开始 AI 批量解析", type="primary"):
            progress_bar = st.progress(0)
            for i, table in enumerate(st.session_state.metadata):
                with st.status(f"正在解析表: {table['table_name']}...", expanded=False):
                    ai_result = analyze_table_with_ai(
                        table, 
                        st.session_state.base_url, 
                        st.session_state.api_key, 
                        st.session_state.model
                    )
                    table['ai_analysis'] = ai_result
                progress_bar.progress((i + 1) / len(st.session_state.metadata))
            st.success("AI 批量解析完成！")
            st.rerun()
            
        for table in st.session_state.metadata:
            with st.expander(f"表: {table['table_name']} - 业务解析"):
                if 'ai_analysis' in table:
                    st.markdown(table['ai_analysis'])
                else:
                    st.write("尚未进行 AI 解析。")

    with tab3:
        st.subheader("导出数据库文档")
        export_format = st.selectbox("导出格式", ["Markdown", "HTML", "JSON"])
        
        if st.button("生成并下载文档"):
            # 这里可以调用导出逻辑
            st.write("导出功能正在开发中...")
            st.download_button(
                label="下载 JSON 元数据",
                data=json.dumps(st.session_state.metadata, indent=4, ensure_ascii=False),
                file_name="metadata.json",
                mime="application/json"
            )
else:
    st.info("请在左侧配置数据库连接并点击“连接”开始。")
    
    # 展示原理文档链接
    st.divider()
    st.markdown("### 📖 更多信息")
    st.markdown("- [查看软件原理与故障排除文档](./PRINCIPLES.md)")
    st.markdown("- [GitHub 仓库](https://github.com/xuebailiang-svg/SmartDB-Doc-linux)")
