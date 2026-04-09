import openai
import json
from datetime import date, datetime
from decimal import Decimal

class DateEncoder(json.JSONEncoder):
    """自定义 JSON 编码器，支持 date, datetime, Decimal 等特殊类型"""
    def default(self, obj):
        if isinstance(obj, (date, datetime)):
            return obj.isoformat()
        elif isinstance(obj, Decimal):
            # 将 Decimal 转换为 float 或 int（如果是整数）
            if obj % 1 == 0:
                return int(obj)
            else:
                return float(obj)
        return super().default(obj)

def analyze_table_with_ai(api_key, base_url, model, table_metadata):
    """
    调用 LLM 接口分析数据库表结构，生成业务含义和关系描述
    支持参考样本数据进行推断，适配多种数据库
    """
    client = openai.OpenAI(api_key=api_key, base_url=base_url)
    
    # 提取样本数据（如果有）
    sample_data_str = ""
    if table_metadata.get('sample_data'):
        sample_data_str = f"\n样本数据 (前5行):\n{json.dumps(table_metadata['sample_data'], indent=2, ensure_ascii=False, cls=DateEncoder)}"
    
    # 构造 Prompt，强调参考样本数据和跨数据库特征
    prompt = f"""
    你是一名资深的数据库架构师。请根据以下数据库表的元数据和样本数据，推断其“中文业务含义”以及“字段的业务解释”。
    
    表名: {table_metadata['table_name']}
    原始备注: {table_metadata['table_comment']}
    
    字段列表:
    {json.dumps(table_metadata['columns'], indent=2, ensure_ascii=False)}
    {sample_data_str}
    
    任务要求:
    1. 结合表名、字段名和样本数据的内容，推断该表在业务系统中的实际用途。
    2. 如果字段备注缺失，请重点参考样本数据的值（例如：如果是 '01', '02'，推断其为状态码；如果是 '20231027'，推断其为日期；如果是加密字符串，推断其为密码或哈希）。
    3. 输出 JSON 格式的结果，包含以下字段：
       - business_name: 表的中文业务名称
       - business_description: 表的业务功能描述
       - columns_explanation: 一个对象，Key 是字段名，Value 是该字段的中文业务解释
    
    仅输出 JSON，不要包含任何其他文字。
    """
    
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "你是一个专业的数据库文档生成助手，擅长通过元数据和样本数据推断业务逻辑。"},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"}
        )
        
        result = json.loads(response.choices[0].message.content)
        return result
    except Exception as e:
        return {
            "business_name": table_metadata['table_name'],
            "business_description": "AI 解析失败: " + str(e),
            "columns_explanation": {col['name']: col.get('comment', '') for col in table_metadata['columns']}
        }

def generate_er_diagram_mermaid(tables_metadata):
    """
    根据数据库元数据生成 Mermaid ER 图代码
    """
    mermaid_code = "erDiagram\n"
    
    for table in tables_metadata:
        table_name = table['table_name']
        mermaid_code += f"    {table_name} {{\n"
        for col in table['columns']:
            # 简化类型显示
            col_type = col['type'].split('(')[0]
            pk_mark = "PK" if col['is_pk'] else ""
            mermaid_code += f"        {col_type} {col['name']} {pk_mark}\n"
        mermaid_code += "    }\n"
        
        # 添加外键关系
        for fk in table.get('foreign_keys', []):
            referred_table = fk['referred_table']
            # 简化关系表示，假设是多对一
            mermaid_code += f"    {table_name} }}|--|| {referred_table} : \"{fk['constrained_columns'][0]}\"\n"
            
    return mermaid_code
