import streamlit as st
import pandas as pd
from db_utils import get_engine, get_schema_metadata
from ai_utils import analyze_table_with_ai, generate_er_diagram_mermaid
from doc_utils import generate_markdown, generate_docx
import io

st.set_page_config(page_title="SmartDB-Doc 全能数据库文档自动化工具 (Windows版)", layout="wide")

# 初始化 Session State
if 'metadata' not in st.session_state:
    st.session_state.metadata = None
if 'ai_results' not in st.session_state:
    st.session_state.ai_results = {}
if 'er_diagram' not in st.session_state:
    st.session_state.er_diagram = ""
if 'api_key' not in st.session_state:
    st.session_state.api_key = ""
if 'base_url' not in st.session_state:
    st.session_state.base_url = "https://api.openai.com/v1"
if 'model' not in st.session_state:
    st.session_state.model = "gpt-4o"

st.title("🚀 SmartDB-Doc: 全能数据库文档自动化生成工具")
st.markdown("---")

# 侧边栏配置
with st.sidebar:
    st.header("🔌 数据库连接配置")
    db_type = st.selectbox("数据库类型", ["Oracle", "MySQL", "PostgreSQL", "SQL Server", "YashanDB"])
    
    host = st.text_input("Host", "localhost")
    
    # 根据数据库类型设置默认端口
    default_port = "1521"
    if db_type == "MySQL": default_port = "3306"
    elif db_type == "PostgreSQL": default_port = "5432"
    elif db_type == "SQL Server": default_port = "1433"
    elif db_type == "YashanDB": default_port = "1688"
    
    port = st.text_input("Port", default_port)
    user = st.text_input("User", "root" if db_type == "MySQL" else "system")
    password = st.text_input("Password", type="password")
    
    db_label = "Service Name / SID" if db_type == "Oracle" else "Database Name"
    database = st.text_input(db_label, "orcl" if db_type == "Oracle" else "test_db")
    
    st.header("🔍 提取范围配置")
    scope_type = st.radio("提取范围", ["全库", "指定 Schema", "指定表"])
    
    target_schema = None
    target_tables = None
    
    if scope_type == "指定 Schema":
        target_schema = st.text_input("请输入 Schema 名称 (如 Oracle 用户名, PG 的 public 等)", "")
    elif scope_type == "指定表":
        target_schema = st.text_input("请输入 Schema 名称 (可选)", "")
        target_tables = st.text_area("请输入表名 (多个请用逗号分隔)", "")
    
    st.header("📊 数据采样配置")
    enable_sampling = st.checkbox("启用样本数据采样 (抓取前5行)", value=False, help="开启后，AI 将参考真实数据内容进行推断，解析更准确。")
    
    st.header("🤖 AI API 配置")
    
    # 模型提供商选择
    model_provider = st.selectbox(
        "模型提供商", 
        ["OpenAI", "DeepSeek", "自定义"],
        index=0 if st.session_state.base_url == "https://api.openai.com/v1" else 1 if st.session_state.base_url == "https://api.deepseek.com/v1" else 2
    )
    
    # 根据模型提供商选择模型
    if model_provider == "OpenAI":
        model_options = ["gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"]
        default_model = "gpt-4o"
        default_base_url = "https://api.openai.com/v1"
    elif model_provider == "DeepSeek":
        model_options = ["deepseek-chat", "deepseek-llm"]
        default_model = "deepseek-chat"
        default_base_url = "https://api.deepseek.com/v1"
    else:  # 自定义
        model_options = []
        default_model = st.session_state.model
        default_base_url = st.session_state.base_url
    
    # 模型选择
    if model_options:
        selected_model = st.selectbox("模型", model_options, index=model_options.index(st.session_state.model) if st.session_state.model in model_options else 0)
        base_url = st.text_input("Base URL", value=default_base_url)
        model = selected_model
    else:
        base_url = st.text_input("Base URL", value=default_base_url)
        model = st.text_input("Model", value=default_model)
    
    # API Key输入
    api_key = st.text_input("API Key", value=st.session_state.api_key, type="password")
    
    # 更新 Session State
    st.session_state.api_key = api_key
    st.session_state.base_url = base_url
    st.session_state.model = model
    
    connect_btn = st.button(f"连接 {db_type} 并提取元数据", use_container_width=True)

# 连接数据库逻辑
if connect_btn:
    try:
        with st.spinner(f"正在连接 {db_type} 并提取元数据..."):
            engine = get_engine(db_type, host, port, user, password, database)
            st.session_state.metadata = get_schema_metadata(
                engine, 
                scope_type=scope_type, 
                target_schema=target_schema if target_schema else None, 
                target_tables=target_tables,
                enable_sampling=enable_sampling
            )
            st.session_state.er_diagram = generate_er_diagram_mermaid(st.session_state.metadata)
            st.success(f"成功提取 {len(st.session_state.metadata)} 张表的元数据！")
    except Exception as e:
        st.error(f"连接失败: {str(e)}")
        if db_type == "Oracle":
            st.info("提示：如果连接 Oracle 11g 失败，请确保已安装 Oracle Instant Client 并配置 PATH。")
        elif db_type == "SQL Server":
            st.info("提示：请确保已安装 ODBC Driver 17/18 for SQL Server。")
        elif db_type == "YashanDB":
            st.info("提示：请确保已安装 YashanDB Python 驱动 (yasdb)。如果使用 SQLAlchemy 模式，还需安装 yashandb_sqlalchemy 方言库。")

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
        st.subheader("AI 业务含义解析")
        if not api_key:
            st.warning("请在侧边栏配置 API Key 以启用 AI 解析功能。")
        else:
            if st.button("开始 AI 批量解析"):
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                for i, table in enumerate(st.session_state.metadata):
                    table_name = table['table_name']
                    status_text.text(f"正在解析表: {table_name} ({i+1}/{len(st.session_state.metadata)})")
                    
                    # 调用 AI
                    ai_res = analyze_table_with_ai(api_key, base_url, model, table)
                    st.session_state.ai_results[table_name] = ai_res
                    
                    # 更新进度
                    progress_bar.progress((i + 1) / len(st.session_state.metadata))
                
                status_text.text("AI 解析完成！")
                st.success("所有表已解析完毕。")
        
        # 显示 AI 解析结果
        if st.session_state.ai_results:
            for table_name, res in st.session_state.ai_results.items():
                with st.expander(f"AI 解析: {table_name} -> {res.get('business_name')}"):
                    st.write(f"**业务描述**: {res.get('business_description')}")
                    st.json(res.get('columns_explanation'))

    with tab3:
        st.subheader("文档预览与下载")
        
        # 生成 Markdown
        md_content = generate_markdown(
            st.session_state.metadata, 
            st.session_state.ai_results, 
            st.session_state.er_diagram
        )
        
        col1, col2 = st.columns(2)
        with col1:
            st.download_button(
                label="📥 下载 Markdown (.md)",
                data=md_content,
                file_name="Database_Doc.md",
                mime="text/markdown",
                use_container_width=True
            )
        with col2:
            # 生成 DOCX
            docx_io = generate_docx(st.session_state.metadata, st.session_state.ai_results)
            st.download_button(
                label="📥 下载 Word (.docx)",
                data=docx_io,
                file_name="Database_Doc.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True
            )
            
        st.markdown("### 实时预览 (Markdown)")
        st.markdown(md_content)
        
        # 渲染 Mermaid
        st.markdown("### 数据库 ER 图 (Mermaid)")
        st.code(st.session_state.er_diagram, language="mermaid")

else:
    st.info(f"请在左侧配置 {db_type} 连接并点击“连接”开始。")
