from langchain_core.tools import tool
from app.services.vector_store import vector_store
from app.services.es_search import ESSearchService
from app.services.graph_service import graph_service

@tool
async def search_financial_vectors(query: str,user_id:str="user_001") -> str:
    """当用户询问财报中的具体概念、业务描述、战略规划时，使用此工具进行语义检索。"""
    docs = await vector_store.search(query,user_id=user_id,top_k=3)
    return "\n".join([d["parent_content"] for d in docs])

@tool
async def search_financial_keywords(query: str,user_id:str) -> str:
    """当用户询问具体的财务数字（如收入、利润、股息率）或特定年份时，使用此工具进行精确匹配。"""
    es = ESSearchService()
    docs = await es.search(query,user_id=user_id,top_k=3)
    return "\n".join([d["parent_content"] for d in docs])

@tool
def calculate_math(expression: str) -> str:
    """当需要进行数学计算（如计算增长率、汇率换算）时，使用此工具。输入必须是纯数学表达式，如 '4.5 * 0.91'。"""
    try:
        # 在生产环境请使用安全沙箱，这里为了演示简化
        result = eval(expression)
        return str(result)
    except Exception as e:
        return f"计算错误: {e}"

# 将工具打包
financial_tools = [search_financial_vectors, search_financial_keywords, calculate_math]