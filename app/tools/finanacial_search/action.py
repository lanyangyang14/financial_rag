from langchain_core.tools import tool
from app.services.vector_store import vector_store
from app.services.es_search import ESSearchService
# ... 引入你的其他依赖 ...

@tool
async def search_financial_vectors(query: str, user_id: str = "user_001") -> str:
    """当用户询问财报中的具体概念、业务描述、战略规划时，使用此工具进行语义检索。"""
    docs = await vector_store.search(query, user_id=user_id, top_k=3)
    return "\n".join([d["parent_content"] for d in docs])

@tool
async def search_financial_keywords(query: str, user_id: str = "user_001") -> str:
    """当用户询问具体的财务数字或特定年份时，使用此工具进行精确匹配。"""
    es = ESSearchService()
    docs = await es.search(query, user_id=user_id, top_k=3)
    return "\n".join([d["parent_content"] for d in docs])