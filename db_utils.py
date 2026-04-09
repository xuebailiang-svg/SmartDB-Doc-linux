import sqlalchemy
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import URL
import pandas as pd
import oracledb
import os

# 尝试导入 yasdb 驱动
try:
    import yasdb
    YASDB_AVAILABLE = True
    print('YASDB_AVAILABLE = True')
except ImportError as e:
    YASDB_AVAILABLE = False
    print('YASDB_AVAILABLE = False, error:', str(e))

# 尝试初始化 Oracle Client (Thick Mode)
try:
    oracledb.init_oracle_client()
    print("Oracle Thick Mode initialized successfully via PATH.")
except Exception as e:
    print(f"Oracle Client initialization info: {e}")

def get_engine(db_type, host, port, user, password, database):
    """
    创建多数据库引擎，适配 Oracle, MySQL, PostgreSQL, SQL Server, YashanDB
    """
    print(f"get_engine called with: db_type={db_type}, host={host}, port={port}, user={user}, database={database}")
    if db_type == "YashanDB":
        if YASDB_AVAILABLE:
            # 使用 yasdb 直接连接
            print(f"Using yasdb direct connection with host={host}, port={port}, user={user}")
            return {
                "type": "yasdb",
                "connection": {
                    "host": host,
                    "port": port,
                    "user": user,
                    "password": password,
                    "database": database
                }
            }
        else:
            # 尝试使用 sqlalchemy 方言 (如果已安装 yashandb_sqlalchemy)
            try:
                url = f"yashandb://{user}:{password}@{host}:{port}/{database}"
                engine = create_engine(url, pool_pre_ping=True)
                return engine
            except Exception as e:
                raise ImportError(f"YashanDB Python driver (yasdb) is not installed and SQLAlchemy dialect failed: {e}")
    elif db_type == "MySQL":
        # 使用 pymysql 驱动
        url = f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}?charset=utf8mb4"
    elif db_type == "PostgreSQL":
        # 使用 psycopg2 驱动
        url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{database}"
    elif db_type == "Oracle":
        # 使用 oracledb 驱动
        url = f"oracle+oracledb://{user}:{password}@{host}:{port}/?service_name={database}"
    elif db_type == "SQL Server":
        # 使用 pyodbc 驱动，需安装 ODBC Driver 17/18
        connection_string = f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={host},{port};DATABASE={database};UID={user};PWD={password}"
        url = URL.create("mssql+pyodbc", query={"odbc_connect": connection_string})
    else:
        raise ValueError(f"Unsupported database type: {db_type}")
    
    engine = create_engine(
        url,
        pool_pre_ping=True
    )
    return engine

def get_sample_data(engine, table_name, schema=None, limit=5):
    """
    抓取不同数据库的前 N 行样本数据
    """
    # 处理 YashanDB 特殊情况 (直接连接模式)
    if isinstance(engine, dict) and engine.get('type') == 'yasdb':
        conn_info = engine['connection']
        host = conn_info['host']
        port = conn_info['port']
        user = conn_info['user']
        password = conn_info['password']
        
        # YashanDB 中通常直接使用表名即可访问当前用户的表
        # 如果指定了 schema，则使用 schema.table_name
        full_name = f'"{schema}"."{table_name}"' if schema else f'"{table_name}"'
        
        try:
            dsn = f"{host}:{port}"
            conn = yasdb.connect(
                dsn=dsn,
                user=user,
                password=password
            )
            cursor = conn.cursor()
            
            # YashanDB 支持 LIMIT 语法
            cursor.execute(f"SELECT * FROM {full_name} LIMIT {limit}")
            rows = cursor.fetchall()
            
            # 获取列名
            column_names = [desc[0] for desc in cursor.description]
            
            # 构建样本数据
            sample_data = []
            for row in rows:
                sample_data.append(dict(zip(column_names, row)))
            
            cursor.close()
            conn.close()
            return sample_data
        except Exception as e:
            print(f"Failed to fetch sample data for {table_name}: {e}")
            return []
    
    # 其他数据库使用 SQLAlchemy
    db_type = engine.dialect.name
    
    # 处理表名转义
    if db_type == 'mysql':
        full_table_name = f'`{table_name}`'
    elif db_type == 'mssql':
        full_table_name = f'[{schema}].[{table_name}]' if schema else f'[{table_name}]'
    elif db_type == 'yashandb':
        full_table_name = f'"{schema}"."{table_name}"' if schema else f'"{table_name}"'
    else:
        full_table_name = f'"{schema}"."{table_name}"' if schema else f'"{table_name}"'
    
    # 根据数据库类型构造采样 SQL
    if db_type == 'oracle':
        query = f"SELECT * FROM (SELECT * FROM {full_table_name}) WHERE ROWNUM <= {limit}"
    elif db_type == 'mssql':
        query = f"SELECT TOP {limit} * FROM {full_table_name}"
    else: # MySQL, PostgreSQL, YashanDB
        query = f"SELECT * FROM {full_table_name} LIMIT {limit}"
        
    try:
        with engine.connect() as conn:
            df = pd.read_sql(text(query), conn)
            return df.to_dict(orient='records')
    except Exception as e:
        print(f"Failed to fetch sample data for {table_name}: {e}")
        return []

def get_schema_metadata(engine, scope_type="全库", target_schema=None, target_tables=None, enable_sampling=False):
    """
    提取数据库元数据，支持范围筛选和样本数据采样
    """
    # 处理 YashanDB 特殊情况 (直接连接模式)
    if isinstance(engine, dict) and engine.get('type') == 'yasdb':
        return get_yashandb_metadata(engine, scope_type, target_schema, target_tables, enable_sampling)
    
    # 其他数据库使用 SQLAlchemy inspector
    inspector = inspect(engine)
    db_type = engine.dialect.name
    
    # 处理默认 Schema
    if not target_schema:
        if db_type == 'oracle':
            target_schema = engine.url.username.upper()
        elif db_type == 'postgresql':
            target_schema = 'public'
        elif db_type == 'mssql':
            target_schema = 'dbo'
        elif db_type == 'yashandb':
            target_schema = engine.url.username.upper()
    
    # 获取表名列表
    if scope_type == "全库" or scope_type == "指定 Schema":
        table_names = inspector.get_table_names(schema=target_schema)
    elif scope_type == "指定表":
        if target_tables:
            requested_tables = [t.strip() for t in target_tables.split(',') if t.strip()]
            all_available = inspector.get_table_names(schema=target_schema)
            table_names = [t for t in requested_tables if t in all_available]
        else:
            table_names = []
    else:
        table_names = inspector.get_table_names(schema=target_schema)
    
    tables_metadata = []
    
    for table_name in table_names:
        try:
            table_comment = inspector.get_table_comment(table_name, schema=target_schema).get('text')
        except:
            table_comment = ""
            
        columns = inspector.get_columns(table_name, schema=target_schema)
        pk_constraint = inspector.get_pk_constraint(table_name, schema=target_schema)
        pk_columns = pk_constraint.get('constrained_columns', [])
        fk_constraints = inspector.get_foreign_keys(table_name, schema=target_schema)
        
        cols_metadata = []
        for col in columns:
            cols_metadata.append({
                "name": col['name'],
                "type": str(col['type']),
                "nullable": col['nullable'],
                "default": str(col.get('default', '')),
                "is_pk": col['name'] in pk_columns,
                "comment": col.get('comment', '')
            })
            
        sample_data = []
        if enable_sampling:
            sample_data = get_sample_data(engine, table_name, schema=target_schema)
            
        tables_metadata.append({
            "table_name": table_name,
            "table_comment": table_comment or "",
            "columns": cols_metadata,
            "foreign_keys": fk_constraints,
            "sample_data": sample_data
        })
        
    return tables_metadata

def get_yashandb_metadata(engine_config, scope_type="全库", target_schema=None, target_tables=None, enable_sampling=False):
    """
    使用 yasdb 直接获取 YashanDB 元数据，适配 23.4 版本
    使用 Oracle 兼容的系统视图 (USER_TABLES, USER_TAB_COLUMNS 等)
    """
    conn_info = engine_config['connection']
    host = conn_info['host']
    port = conn_info['port']
    user = conn_info['user']
    password = conn_info['password']
    
    dsn = f"{host}:{port}"
    print(f"Connecting to YashanDB with dsn={dsn}, user={user}")
    
    conn = yasdb.connect(
        dsn=dsn,
        user=user,
        password=password
    )
    
    cursor = conn.cursor()
    tables_metadata = []
    
    try:
        # 1. 获取表名列表和注释
        # 如果是“全库”或“指定 Schema”，我们查询当前用户或指定用户的表
        # 注意：YashanDB 的 USER_TABLES 只显示当前用户的表
        if scope_type == "指定 Schema" and target_schema and target_schema.upper() != user.upper():
            # 查询指定 Schema (需要有权限访问 ALL_TABLES)
            table_query = f"SELECT t.TABLE_NAME, c.COMMENTS FROM ALL_TABLES t LEFT JOIN ALL_TAB_COMMENTS c ON t.TABLE_NAME = c.TABLE_NAME AND t.OWNER = c.OWNER WHERE t.OWNER = '{target_schema.upper()}'"
            owner_filter = target_schema.upper()
        else:
            # 默认查询当前用户的表
            table_query = "SELECT t.TABLE_NAME, c.COMMENTS FROM USER_TABLES t LEFT JOIN USER_TAB_COMMENTS c ON t.TABLE_NAME = c.TABLE_NAME"
            owner_filter = user.upper()

        if scope_type == "指定表" and target_tables:
            requested_tables = [f"'{t.strip().upper()}'" for t in target_tables.split(',') if t.strip()]
            if requested_tables:
                table_query += f" AND t.TABLE_NAME IN ({','.join(requested_tables)})"

        print(f"Executing table query: {table_query}")
        cursor.execute(table_query)
        table_info = cursor.fetchall()
        
        for table_name, table_comment in table_info:
            print(f"Processing table: {table_name}")
            
            # 2. 获取列信息
            if owner_filter == user.upper():
                col_query = f"SELECT COLUMN_NAME, DATA_TYPE, NULLABLE, DATA_DEFAULT FROM USER_TAB_COLUMNS WHERE TABLE_NAME = '{table_name}' ORDER BY COLUMN_ID"
                comm_query = f"SELECT COLUMN_NAME, COMMENTS FROM USER_COL_COMMENTS WHERE TABLE_NAME = '{table_name}'"
            else:
                col_query = f"SELECT COLUMN_NAME, DATA_TYPE, NULLABLE, DATA_DEFAULT FROM ALL_TAB_COLUMNS WHERE TABLE_NAME = '{table_name}' AND OWNER = '{owner_filter}' ORDER BY COLUMN_ID"
                comm_query = f"SELECT COLUMN_NAME, COMMENTS FROM ALL_COL_COMMENTS WHERE TABLE_NAME = '{table_name}' AND OWNER = '{owner_filter}'"

            cursor.execute(col_query)
            columns = cursor.fetchall()
            
            cursor.execute(comm_query)
            comments_dict = {row[0]: row[1] for row in cursor.fetchall()}
            
            # 3. 获取主键信息
            if owner_filter == user.upper():
                pk_query = f"SELECT COLUMN_NAME FROM USER_CONS_COLUMNS WHERE CONSTRAINT_NAME IN (SELECT CONSTRAINT_NAME FROM USER_CONSTRAINTS WHERE TABLE_NAME = '{table_name}' AND CONSTRAINT_TYPE = 'P')"
            else:
                pk_query = f"SELECT COLUMN_NAME FROM ALL_CONS_COLUMNS WHERE OWNER = '{owner_filter}' AND CONSTRAINT_NAME IN (SELECT CONSTRAINT_NAME FROM ALL_CONSTRAINTS WHERE TABLE_NAME = '{table_name}' AND OWNER = '{owner_filter}' AND CONSTRAINT_TYPE = 'P')"
            
            cursor.execute(pk_query)
            pk_columns = [row[0] for row in cursor.fetchall()]
            
            # 构建列元数据
            cols_metadata = []
            for col in columns:
                cols_metadata.append({
                    "name": col[0],
                    "type": col[1],
                    "nullable": col[2] == 'Y',
                    "default": str(col[3]) if col[3] is not None else "",
                    "is_pk": col[0] in pk_columns,
                    "comment": comments_dict.get(col[0], "") or ""
                })
            
            # 4. 获取外键信息
            fk_constraints = []
            if owner_filter == user.upper():
                fk_query = f"""
                    SELECT a.CONSTRAINT_NAME, a.COLUMN_NAME, b.OWNER as REFERRED_SCHEMA, b.TABLE_NAME as REFERRED_TABLE, b.COLUMN_NAME as REFERRED_COLUMN
                    FROM USER_CONS_COLUMNS a
                    JOIN USER_CONSTRAINTS c ON a.CONSTRAINT_NAME = c.CONSTRAINT_NAME
                    JOIN USER_CONS_COLUMNS b ON c.R_CONSTRAINT_NAME = b.CONSTRAINT_NAME
                    WHERE c.TABLE_NAME = '{table_name}' AND c.CONSTRAINT_TYPE = 'R'
                """
            else:
                fk_query = f"""
                    SELECT a.CONSTRAINT_NAME, a.COLUMN_NAME, b.OWNER as REFERRED_SCHEMA, b.TABLE_NAME as REFERRED_TABLE, b.COLUMN_NAME as REFERRED_COLUMN
                    FROM ALL_CONS_COLUMNS a
                    JOIN ALL_CONSTRAINTS c ON a.CONSTRAINT_NAME = c.CONSTRAINT_NAME AND a.OWNER = c.OWNER
                    JOIN ALL_CONS_COLUMNS b ON c.R_CONSTRAINT_NAME = b.CONSTRAINT_NAME AND c.R_OWNER = b.OWNER
                    WHERE c.TABLE_NAME = '{table_name}' AND c.OWNER = '{owner_filter}' AND c.CONSTRAINT_TYPE = 'R'
                """
            
            cursor.execute(fk_query)
            fk_rows = cursor.fetchall()
            
            fk_dict = {}
            for row in fk_rows:
                c_name = row[0]
                if c_name not in fk_dict:
                    fk_dict[c_name] = {
                        "name": c_name,
                        "constrained_columns": [],
                        "referred_schema": row[2],
                        "referred_table": row[3],
                        "referred_columns": []
                    }
                fk_dict[c_name]["constrained_columns"].append(row[1])
                fk_dict[c_name]["referred_columns"].append(row[4])
            
            fk_constraints = list(fk_dict.values())
            
            # 5. 获取样本数据
            sample_data = []
            if enable_sampling:
                try:
                    full_table_name = f'"{owner_filter}"."{table_name}"'
                    cursor.execute(f"SELECT * FROM {full_table_name} LIMIT 5")
                    rows = cursor.fetchall()
                    column_names = [desc[0] for desc in cursor.description]
                    for row in rows:
                        sample_data.append(dict(zip(column_names, row)))
                except Exception as e:
                    print(f"Failed to fetch sample data for {table_name}: {e}")
            
            tables_metadata.append({
                "table_name": table_name,
                "table_comment": table_comment or "",
                "columns": cols_metadata,
                "foreign_keys": fk_constraints,
                "sample_data": sample_data
            })
    finally:
        cursor.close()
        conn.close()
    
    return tables_metadata
