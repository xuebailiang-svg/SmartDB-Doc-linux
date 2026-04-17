import sqlalchemy
from sqlalchemy import create_engine, inspect, text, event
from sqlalchemy.engine import URL
import pandas as pd
import oracledb
import os

# 尝试导入 yasdb 驱动
try:
    import yasdb
    YASDB_AVAILABLE = True
except ImportError:
    YASDB_AVAILABLE = False

# 尝试初始化 Oracle Client (Thick Mode)
try:
    oracledb.init_oracle_client()
    print("Oracle Thick Mode initialized successfully.")
except Exception as e:
    print(f"Oracle Client initialization info (Using Thin Mode): {e}")

def get_engine(db_type, host, port, user, password, database):
    """
    创建多数据库引擎，适配 Oracle, MySQL, PostgreSQL, SQL Server, YashanDB
    """
    if db_type == "YashanDB":
        if YASDB_AVAILABLE:
            return {
                "type": "yasdb",
                "connection": {"host": host, "port": port, "user": user, "password": password, "database": database}
            }
        else:
            url = f"yashandb://{user}:{password}@{host}:{port}/{database}"
    elif db_type == "MySQL":
        url = f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}?charset=utf8mb4"
    elif db_type == "PostgreSQL":
        url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{database}"
    elif db_type == "Oracle":
        # 核心修复：通过 creator 手动控制连接过程，强制字符集协商
        def create_oracle_connection():
            # 强制设置环境变量
            os.environ["NLS_LANG"] = "AMERICAN_AMERICA.AL32UTF8"
            # 构造连接参数，显式指定编码
            conn = oracledb.connect(
                user=user,
                password=password,
                dsn=f"{host}:{port}/{database}",
                encoding="UTF-8",
                nencoding="UTF-8"
            )
            return conn
        
        # 使用 creator 模式绕过 SQLAlchemy 默认的连接行为
        engine = create_engine("oracle+oracledb://", creator=create_oracle_connection, pool_pre_ping=True)
        return engine
    elif db_type == "SQL Server":
        connection_string = f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={host},{port};DATABASE={database};UID={user};PWD={password}"
        url = URL.create("mssql+pyodbc", query={"odbc_connect": connection_string})
    else:
        raise ValueError(f"Unsupported database type: {db_type}")
    
    engine = create_engine(url, pool_pre_ping=True)
    return engine

def get_oracle_metadata_native(engine, scope_type, target_schema, target_tables, enable_sampling):
    """
    使用原生 SQL 提取 Oracle 元数据，彻底解决乱码问题
    """
    tables_metadata = []
    user_upper = target_schema.upper() if target_schema else engine.url.username.upper() if engine.url.username else user.upper()
    
    with engine.connect() as conn:
        # 1. 获取表列表和注释
        table_sql = f"SELECT TABLE_NAME, COMMENTS FROM ALL_TAB_COMMENTS WHERE OWNER = '{user_upper}' AND TABLE_TYPE = 'TABLE'"
        if scope_type == "指定表" and target_tables:
            table_list = ",".join([f"'{t.strip().upper()}'" for t in target_tables.split(",") if t.strip()])
            if table_list:
                table_sql += f" AND TABLE_NAME IN ({table_list})"
        
        df_tables = pd.read_sql(text(table_sql), conn)
        
        for _, row in df_tables.iterrows():
            table_name = row['table_name']
            table_comment = row['comments']
            
            # 2. 获取列信息和注释
            col_sql = f"""
                SELECT 
                    t.COLUMN_NAME, t.DATA_TYPE, t.NULLABLE, t.DATA_DEFAULT, c.COMMENTS
                FROM ALL_TAB_COLUMNS t
                LEFT JOIN ALL_COL_COMMENTS c ON t.OWNER = c.OWNER AND t.TABLE_NAME = c.TABLE_NAME AND t.COLUMN_NAME = c.COLUMN_NAME
                WHERE t.OWNER = '{user_upper}' AND t.TABLE_NAME = '{table_name}'
                ORDER BY t.COLUMN_ID
            """
            df_cols = pd.read_sql(text(col_sql), conn)
            
            # 3. 获取主键
            pk_sql = f"""
                SELECT cols.column_name
                FROM all_constraints cons, all_cons_columns cols
                WHERE cons.owner = '{user_upper}' 
                AND cons.table_name = '{table_name}'
                AND cons.constraint_type = 'P'
                AND cons.constraint_name = cols.constraint_name
                AND cons.owner = cols.owner
            """
            pk_cols = pd.read_sql(text(pk_sql), conn)['column_name'].tolist()
            
            cols_metadata = []
            for _, col in df_cols.iterrows():
                cols_metadata.append({
                    "name": col['column_name'],
                    "type": str(col['data_type']),
                    "nullable": col['nullable'] == 'Y',
                    "default": str(col['data_default']) if col['data_default'] is not None else "",
                    "is_pk": col['column_name'] in pk_cols,
                    "comment": col['comments'] or ""
                })
            
            sample_data = get_sample_data(engine, table_name, schema=user_upper) if enable_sampling else []
                
            tables_metadata.append({
                "table_name": table_name,
                "table_comment": table_comment or "",
                "columns": cols_metadata,
                "foreign_keys": [],
                "sample_data": sample_data
            })
            
    return tables_metadata

def get_sample_data(engine, table_name, schema=None, limit=5):
    """
    抓取样本数据
    """
    if isinstance(engine, dict) and engine.get('type') == 'yasdb':
        conn_info = engine['connection']
        try:
            conn = yasdb.connect(dsn=f"{conn_info['host']}:{conn_info['port']}", user=conn_info['user'], password=conn_info['password'])
            cursor = conn.cursor()
            full_name = f'"{schema}"."{table_name}"' if schema else f'"{table_name}"'
            cursor.execute(f"SELECT * FROM {full_name} LIMIT {limit}")
            rows = cursor.fetchall()
            column_names = [desc[0] for desc in cursor.description]
            data = [dict(zip(column_names, row)) for row in rows]
            cursor.close()
            conn.close()
            return data
        except: return []

    db_type = engine.dialect.name
    full_table_name = f'"{schema}"."{table_name}"' if schema else f'"{table_name}"'
    if db_type == 'mysql': full_table_name = f'`{table_name}`'
    
    if db_type == 'oracle':
        query = f"SELECT * FROM (SELECT * FROM {full_table_name}) WHERE ROWNUM <= {limit}"
    else:
        query = f"SELECT * FROM {full_table_name} LIMIT {limit}"
        
    try:
        with engine.connect() as conn:
            df = pd.read_sql(text(query), conn)
            return df.to_dict(orient='records')
    except: return []

def get_schema_metadata(engine, scope_type="全库", target_schema=None, target_tables=None, enable_sampling=False):
    """
    提取元数据主入口
    """
    if isinstance(engine, dict) and engine.get('type') == 'yasdb':
        return get_yashandb_metadata(engine, scope_type, target_schema, target_tables, enable_sampling)
    
    db_type = engine.dialect.name
    if db_type == 'oracle':
        try:
            return get_oracle_metadata_native(engine, scope_type, target_schema, target_tables, enable_sampling)
        except Exception as e:
            print(f"Native Oracle metadata extraction failed: {e}")

    inspector = inspect(engine)
    if not target_schema:
        target_schema = engine.url.username.upper() if engine.url.username else None
    
    table_names = inspector.get_table_names(schema=target_schema)
    if scope_type == "指定表" and target_tables:
        requested = [t.strip() for t in target_tables.split(',') if t.strip()]
        table_names = [t for t in requested if t in table_names]
    
    tables_metadata = []
    for table_name in table_names:
        try:
            table_comment = inspector.get_table_comment(table_name, schema=target_schema).get('text')
        except: table_comment = ""
        columns = inspector.get_columns(table_name, schema=target_schema)
        pk_columns = inspector.get_pk_constraint(table_name, schema=target_schema).get('constrained_columns', [])
        cols_metadata = []
        for col in columns:
            cols_metadata.append({
                "name": col['name'], "type": str(col['type']), "nullable": col['nullable'],
                "default": str(col.get('default', '')), "is_pk": col['name'] in pk_columns,
                "comment": col.get('comment', '')
            })
        sample_data = get_sample_data(engine, table_name, schema=target_schema) if enable_sampling else []
        tables_metadata.append({
            "table_name": table_name, "table_comment": table_comment or "",
            "columns": cols_metadata, "foreign_keys": [], "sample_data": sample_data
        })
    return tables_metadata

def get_yashandb_metadata(engine_config, scope_type, target_schema, target_tables, enable_sampling):
    """
    使用 yasdb 直接获取 YashanDB 元数据
    """
    conn_info = engine_config['connection']
    conn = yasdb.connect(dsn=f"{conn_info['host']}:{conn_info['port']}", user=conn_info['user'], password=conn_info['password'])
    cursor = conn.cursor()
    tables_metadata = []
    try:
        user = conn_info['user'].upper()
        if scope_type == "指定 Schema" and target_schema and target_schema.upper() != user:
            table_query = f"SELECT t.TABLE_NAME, c.COMMENTS FROM ALL_TABLES t LEFT JOIN ALL_TAB_COMMENTS c ON t.TABLE_NAME = c.TABLE_NAME AND t.OWNER = c.OWNER WHERE t.OWNER = '{target_schema.upper()}'"
            owner_filter = target_schema.upper()
        else:
            table_query = "SELECT t.TABLE_NAME, c.COMMENTS FROM USER_TABLES t LEFT JOIN USER_TAB_COMMENTS c ON t.TABLE_NAME = c.TABLE_NAME"
            owner_filter = user

        if scope_type == "指定表" and target_tables:
            requested = ",".join([f"'{t.strip().upper()}'" for t in target_tables.split(',') if t.strip()])
            if requested: table_query += f" AND t.TABLE_NAME IN ({requested})"

        cursor.execute(table_query)
        for table_name, table_comment in cursor.fetchall():
            col_query = f"SELECT COLUMN_NAME, DATA_TYPE, NULLABLE, DATA_DEFAULT FROM {'ALL' if owner_filter != user else 'USER'}_TAB_COLUMNS WHERE TABLE_NAME = '{table_name}'"
            if owner_filter != user: col_query += f" AND OWNER = '{owner_filter}'"
            cursor.execute(col_query)
            columns = cursor.fetchall()
            
            comm_query = f"SELECT COLUMN_NAME, COMMENTS FROM {'ALL' if owner_filter != user else 'USER'}_COL_COMMENTS WHERE TABLE_NAME = '{table_name}'"
            if owner_filter != user: comm_query += f" AND OWNER = '{owner_filter}'"
            cursor.execute(comm_query)
            comments_dict = {row[0]: row[1] for row in cursor.fetchall()}
            
            pk_query = f"SELECT COLUMN_NAME FROM {'ALL' if owner_filter != user else 'USER'}_CONS_COLUMNS WHERE TABLE_NAME = '{table_name}' AND CONSTRAINT_NAME IN (SELECT CONSTRAINT_NAME FROM {'ALL' if owner_filter != user else 'USER'}_CONSTRAINTS WHERE CONSTRAINT_TYPE = 'P')"
            if owner_filter != user: pk_query += f" AND OWNER = '{owner_filter}'"
            cursor.execute(pk_query)
            pk_cols = [row[0] for row in cursor.fetchall()]
            
            cols_metadata = []
            for col in columns:
                cols_metadata.append({
                    "name": col[0], "type": col[1], "nullable": col[2] == 'Y',
                    "default": str(col[3]) if col[3] else "", "is_pk": col[0] in pk_cols,
                    "comment": comments_dict.get(col[0], "")
                })
            sample_data = get_sample_data(engine_config, table_name, schema=owner_filter) if enable_sampling else []
            tables_metadata.append({
                "table_name": table_name, "table_comment": table_comment or "",
                "columns": cols_metadata, "foreign_keys": [], "sample_data": sample_data
            })
        return tables_metadata
    finally:
        cursor.close()
        conn.close()
